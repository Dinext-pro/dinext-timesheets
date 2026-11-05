"""Server-side authorization for User Timesheet whitelist API."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import getdate

from dinext_timesheets.timesheet_status import PARENT_DRAFT, PARENT_REWORK


def worker_group(worker: str) -> str | None:
	return frappe.db.get_value("Worker", {"wuser": worker}, "wuser_group")


def has_worker_scope(worker: str, period_end, actor: str | None = None) -> bool:
	actor = actor or frappe.session.user
	if not worker or not period_end or not actor:
		return False
	if actor == worker:
		return True
	group = worker_group(worker)
	if not group:
		return False
	lead = frappe.db.get_value(
		"Teamleads Table",
		{"parent": group, "parenttype": "User Group", "date": ("<=", getdate(period_end))},
		"teamlead",
		order_by="date desc, idx desc",
	)
	return lead == actor


def assert_can_create_for_worker(worker: str, period_end, actor: str | None = None) -> None:
	actor = actor or frappe.session.user
	if not frappe.has_permission("User Timesheet", "create", user=actor) or not has_worker_scope(
		worker, period_end, actor
	):
		frappe.throw(_("Not permitted to create a timesheet for this worker and period"), frappe.PermissionError)


def can_edit_timesheet(doc) -> bool:
	return (
		doc.ut_status in {PARENT_DRAFT, PARENT_REWORK}
		and has_worker_scope(doc.timesheet_from, doc.ts_valid_for)
		and frappe.has_permission(doc, "write", ignore_share_permissions=True)
	)


def assert_can_edit_timesheet(doc) -> None:
	if not can_edit_timesheet(doc):
		frappe.throw(_("Not permitted to edit this timesheet"), frappe.PermissionError)


def timesheet_management_transitions(position) -> list:
	from frappe.model.workflow import get_workflow, get_workflow_name

	if not get_workflow_name(position.doctype):
		return []
	workflow = get_workflow(position.doctype)
	state = position.get(workflow.workflow_state_field)
	return [
		row for row in workflow.transitions
		if row.state == state and row.get("custom_timesheet_management_action")
	]


def assert_can_query_tasks_for_owner(ts_owner: str, start=None, end=None) -> None:
	"""Allow the worker or a caller who can read the requested timesheet."""
	if not (ts_owner and start and end):
		frappe.throw(_("A worker and timesheet period are required"), frappe.PermissionError)

	if frappe.session.user == ts_owner:
		return

	names = frappe.get_list(
		"User Timesheet",
		filters={"timesheet_from": ts_owner, "ts_valid_from": start, "ts_valid_for": end},
		pluck="name",
		limit_page_length=1,
	)
	if names:
		return

	frappe.throw(
		_("Not permitted to load timesheet tasks for user {0}").format(ts_owner),
		frappe.PermissionError,
	)


def assert_can_set_timesheet_status(items, ts_name=None, ts_status=None) -> None:
	"""Caller may write listed UTP and optional parent UT; UTP must belong to ts_name if set."""
	for p in items or []:
		name = p if isinstance(p, str) else (p or {}).get("name")
		if not name:
			continue
		if not frappe.db.exists("User Timesheet Position", name):
			frappe.throw(_("User Timesheet Position {0} not found").format(name))

		position = frappe.get_doc("User Timesheet Position", name)
		if not frappe.has_permission("User Timesheet Position", "write", doc=position):
			frappe.throw(
				_("Not permitted to update {0}").format(name),
				frappe.PermissionError,
			)
		if ts_name and position.user_timesheet and position.user_timesheet != ts_name:
			frappe.throw(
				_("Position {0} does not belong to timesheet {1}").format(
					name, ts_name
				),
				frappe.ValidationError,
			)

	if ts_name and ts_status:
		assert_can_write_timesheet(ts_name)


# Dedicated UT perm bit for «Перепровести» (Role Permission Manager, not role names).
REPROCESS_JE_PERM = "import"


def can_reprocess_journal_entries(user: str | None = None) -> bool:
	"""True if user has User Timesheet import (repost JE). SM/Administrator included."""
	return bool(frappe.has_permission("User Timesheet", REPROCESS_JE_PERM, user=user))


def assert_can_reprocess_journal_entries(user: str | None = None) -> None:
	if not can_reprocess_journal_entries(user):
		frappe.throw(
			_("Not permitted to reprocess timesheet journal entries"),
			frappe.PermissionError,
		)


def assert_can_read_timesheet(ts_name: str) -> None:
	"""Caller may read this User Timesheet (banner / read-only helpers)."""
	if not ts_name:
		frappe.throw(_("Timesheet name is required"), frappe.ValidationError)
	if not frappe.db.exists("User Timesheet", ts_name):
		frappe.throw(_("User Timesheet {0} not found").format(ts_name))
	timesheet = frappe.get_doc("User Timesheet", ts_name)
	if not frappe.has_permission("User Timesheet", "read", doc=timesheet):
		frappe.throw(
			_("Not permitted to read timesheet {0}").format(ts_name),
			frappe.PermissionError,
		)


def assert_can_write_timesheet(ts_name: str) -> None:
	"""Caller may write User Timesheet (copy / status)."""
	if not ts_name:
		frappe.throw(_("Timesheet name is required"), frappe.ValidationError)
	if not frappe.db.exists("User Timesheet", ts_name):
		frappe.throw(_("User Timesheet {0} not found").format(ts_name))
	timesheet = frappe.get_doc("User Timesheet", ts_name)
	if not frappe.has_permission("User Timesheet", "write", doc=timesheet):
		frappe.throw(
			_("Not permitted to update timesheet {0}").format(ts_name),
			frappe.PermissionError,
		)
