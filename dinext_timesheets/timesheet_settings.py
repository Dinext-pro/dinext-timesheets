"""Singleton Timesheet Settings: which status moves the other."""

from __future__ import annotations

import frappe
from frappe import _

from dinext_timesheets.timesheet_status import (
	DEFAULT_HIDDEN_LIST_STATUSES,
	DEFAULT_POSITION_RULES,
	POSITION_STATUS_UNSET,
	first_matching_rule,
)

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
	value = source.get if isinstance(source, dict) else lambda key, default=None: getattr(source, key, default)
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
			frappe.throw(
				_("A timesheet rule for position status {0} is already set").format(status)
			)
		seen_positions.add(status)
		if status == POSITION_STATUS_UNSET or (known and status not in known):
			frappe.throw(
				_("{0} is not a state of the User Timesheet Position workflow").format(status)
			)
		if row.threshold not in {"Any", "All"}:
			frappe.throw(_("Threshold must be Any or All"))
		if getattr(row, "check_timesheet", 0):
			checked_rows += 1
	if checked_rows > 1:
		frappe.throw(_("Timesheet Check can be set on only one row"))
	seen_hidden: set[str] = set()
	for row in getattr(doc, "hidden_list_statuses", None) or []:
		status = row.position_status or ""
		if not status:
			continue
		if status in seen_hidden:
			frappe.throw(
				_("Position status {0} is already hidden from the list").format(status)
			)
		seen_hidden.add(status)
		if status != POSITION_STATUS_UNSET and known and status not in known:
			frappe.throw(
				_("{0} is not a state of the User Timesheet Position workflow").format(status)
			)


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
	for row in DEFAULT_HIDDEN_LIST_STATUSES:
		doc.append("hidden_list_statuses", row)
	doc.save(ignore_permissions=True)


def hidden_list_statuses() -> list[str]:
	"""Statuses omitted from the position list. A saved empty table hides nothing."""
	doc = _settings_doc()
	if doc is None:
		return [row["position_status"] for row in DEFAULT_HIDDEN_LIST_STATUSES]
	return [
		row.position_status
		for row in (getattr(doc, "hidden_list_statuses", None) or [])
		if row.position_status
	]


def hidden_status_values(hidden: list[str]) -> list[str]:
	"""Values compared with ifnull(status, ''). Not Set matches a blank status."""
	values: list[str] = []
	for status in hidden:
		value = "" if status == POSITION_STATUS_UNSET else status
		if value is not None and value not in values:
			values.append(value)
	return values


def utp_list_conditions(user=None) -> str:
	"""Hide configured statuses from the position list. Other queries stay unchanged."""
	del user
	if frappe.form_dict.get("cmd") not in LIST_COMMANDS:
		return ""
	values = hidden_status_values(hidden_list_statuses())
	if not values:
		return ""
	listed = ", ".join(frappe.db.escape(value) for value in values)
	return f"ifnull(`tab{POSITION_DOCTYPE}`.`status`, '') not in ({listed})"


@frappe.whitelist()
def hidden_status_options():
	"""Workflow states, then the blank-status choice, for the hidden-list Select."""
	return [*position_workflow_states(), POSITION_STATUS_UNSET]


@frappe.whitelist()
def utp_state_query(doctype, txt, searchfield, start, page_len, filters):
	"""Link search limited to the active position workflow."""
	del doctype, searchfield, filters
	text = (txt or "").lower()
	start = int(start or 0)
	page_len = int(page_len or 20)
	names = [
		name
		for name in position_workflow_states()
		if not text or text in name.lower()
	]
	return [(name,) for name in names[start : start + page_len]]
