"""Singleton Timesheet Settings: which status moves the other."""

from __future__ import annotations

import frappe
from dinext_timesheets.timesheet_status import (
	DEFAULT_PARENT_RULES,
	DEFAULT_POSITION_RULES,
	DEFAULT_VISIBLE_LIST_STATUSES,
	POSITION_STATUS_UNSET,
	first_matching_rule,
)
from frappe import _
from frappe.query_builder.functions import IfNull
from frappe.utils import cint
from pypika.terms import Criterion, ExistsCriterion

LIST_COMMANDS = {
	"frappe.desk.reportview.get",
	"frappe.desk.reportview.get_count",
	"frappe.desk.reportview.get_sidebar_stats",
}

POSITION_DOCTYPE = "User Timesheet Position"


def position_workflow_states() -> list[str]:
	"""States of the active User Timesheet Position workflow, in workflow order."""
	workflows = frappe.get_all(
		"Workflow",
		filters={"document_type": POSITION_DOCTYPE, "is_active": 1},
		pluck="name",
		order_by="name asc",
	)
	if not workflows:
		return []
	rows = frappe.get_all(
		"Workflow Document State",
		filters={"parent": ("in", workflows), "parenttype": "Workflow"},
		fields=["state", "idx"],
		order_by="idx asc",
	)
	seen: list[str] = []
	for row in rows:
		state = row.get("state") if isinstance(row, dict) else None
		if state and state not in seen:
			seen.append(state)
	return seen


def _settings_doc():
	if not frappe.db.exists("Timesheet Settings", "Timesheet Settings"):
		return None
	return frappe.get_single("Timesheet Settings")


def _position_rule_row(row) -> dict:
	source = row if isinstance(row, dict) else row
	value = (
		source.get if isinstance(source, dict) else lambda key, default=None: getattr(source, key, default)
	)
	return {
		"position_status": value("position_status"),
		"timesheet_status": value("timesheet_status"),
		"threshold": value("threshold"),
		"check_timesheet": int(value("check_timesheet", 0) or 0),
		"move_all_positions": int(value("move_all_positions", 0) or 0),
	}


def position_rules() -> list[dict]:
	"""Saved position-to-timesheet rules. Missing singleton uses the defaults."""
	doc = _settings_doc()
	rows = DEFAULT_POSITION_RULES if doc is None else (doc.position_rules or [])
	result = []
	for row in rows:
		item = _position_rule_row(row)
		if item["position_status"] and item["timesheet_status"] and item["threshold"]:
			result.append(item)
	return result


def timesheet_check_status() -> str | None:
	"""Timesheet status before which filling checks run. None skips the checks."""
	for row in position_rules():
		if row["check_timesheet"]:
			return row["timesheet_status"]
	return None


def parent_position_target(timesheet_status: str) -> str | None:
	"""Position status applied to every position when the timesheet enters timesheet_status."""
	doc = _settings_doc()
	rows = (
		[dict(row) for row in DEFAULT_PARENT_RULES]
		if doc is None
		else [
			{
				"timesheet_status": row.timesheet_status,
				"position_status": row.position_status,
			}
			for row in (doc.get("parent_rules") or [])
		]
	)
	for row in rows:
		if row.get("timesheet_status") == timesheet_status and row.get("position_status"):
			return row["position_status"]
	return None


def usable_position_rules() -> list[dict]:
	"""Drop rules whose position status is no longer in the workflow."""
	known = set(position_workflow_states())
	rules = position_rules()
	if not known:
		return rules
	return [row for row in rules if row["position_status"] in known]


def matching_position_rule(counts: dict[str, int]) -> dict | None:
	return first_matching_rule(usable_position_rules(), counts)


def validate_timesheet_settings(doc) -> None:
	known = set(position_workflow_states())
	seen_positions: set[str] = set()
	checked_rows = 0
	for row in doc.position_rules or []:
		status = row.position_status or ""
		if not status:
			continue
		if status in seen_positions:
			frappe.throw(_("A timesheet rule for position status {0} is already set").format(status))
		seen_positions.add(status)
		if status == POSITION_STATUS_UNSET or (known and status not in known):
			frappe.throw(_("{0} is not a state of the User Timesheet Position workflow").format(status))
		if row.threshold not in {"Any", "All"}:
			frappe.throw(_("Threshold must be Any or All"))
		if getattr(row, "check_timesheet", 0):
			checked_rows += 1
	if checked_rows > 1:
		frappe.throw(_("Timesheet Check can be set on only one row"))
	seen_visible: set[str] = set()
	for row in getattr(doc, "visible_list_statuses", None) or []:
		status = row.position_status or ""
		if not status:
			continue
		if status in seen_visible:
			frappe.throw(_("Position status {0} is already visible in the list").format(status))
		seen_visible.add(status)
		if status != POSITION_STATUS_UNSET and known and status not in known:
			frappe.throw(_("{0} is not a state of the User Timesheet Position workflow").format(status))

	doc.position_list_visibility_migrated = 1


def seed_default_rules() -> None:
	"""Fill an empty singleton. A saved empty table stays empty."""
	if frappe.db.exists("Timesheet Settings", "Timesheet Settings"):
		doc = frappe.get_single("Timesheet Settings")
		if doc.position_rules:
			return
	else:
		doc = frappe.new_doc("Timesheet Settings")
	for row in DEFAULT_POSITION_RULES:
		doc.append("position_rules", row)
	for row in DEFAULT_VISIBLE_LIST_STATUSES:
		doc.append("visible_list_statuses", row)
	doc.position_list_visibility_migrated = 1
	doc.save(ignore_permissions=True)


def visible_list_rules() -> list[dict]:
	"""Explicit display rules. A saved empty table shows no positions."""
	doc = _settings_doc()
	rows = (
		DEFAULT_VISIBLE_LIST_STATUSES if doc is None else (getattr(doc, "visible_list_statuses", None) or [])
	)
	return [
		{
			"position_status": row.get("position_status"),
			"open_wf_task": cint(row.get("open_wf_task")),
		}
		for row in rows
		if row.get("position_status")
	]


def status_values(statuses: list[str]) -> list[str]:
	"""Not Set explicitly includes both blank and NULL position status."""
	return list(dict.fromkeys("" if status == POSITION_STATUS_UNSET else status for status in statuses))


def utp_list_conditions(user=None) -> str:
	"""Display filter for reportview only; composed with existing document permissions."""
	if frappe.form_dict.get("cmd") not in LIST_COMMANDS:
		return ""
	rules = visible_list_rules()
	if not rules:
		return "1=0"
	position = frappe.qb.DocType(POSITION_DOCTYPE)
	status = IfNull(position.status, "")
	plain = status_values([row["position_status"] for row in rules if not row["open_wf_task"]])
	gated = status_values([row["position_status"] for row in rules if row["open_wf_task"]])
	conditions = []
	if plain:
		conditions.append(status.isin(plain))
	if gated:
		task = frappe.qb.DocType("Workflow Task")
		open_tasks = (
			frappe.qb.from_(task)
			.select(task.name)
			.where(
				(task.reference_doctype == POSITION_DOCTYPE)
				& (task.reference_name == position.name)
				& (task.approver == (user or frappe.session.user))
				& (task.status == "Working")
				& (task.round_status == "Open")
			)
		)
		conditions.append(status.isin(gated) & ExistsCriterion(open_tasks))
	condition = Criterion.any(conditions).get_sql(
		quote_char=frappe.qb.from_(position).QUOTE_CHAR,
		with_namespace=True,
		subquery=True,
	)
	return f"({condition})"


@frappe.whitelist()
def visible_status_options():
	"""Workflow states, then the explicit blank-status choice."""
	return [*position_workflow_states(), POSITION_STATUS_UNSET]


@frappe.whitelist()
def utp_state_query(doctype, txt, searchfield, start, page_len, filters):
	"""Link search limited to the active position workflow."""
	del doctype, searchfield, filters
	text = (txt or "").lower()
	start = int(start or 0)
	page_len = int(page_len or 20)
	names = [name for name in position_workflow_states() if not text or text in name.lower()]
	return [(name,) for name in names[start : start + page_len]]
