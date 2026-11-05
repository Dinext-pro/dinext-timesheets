"""User Timesheet Position doc_events (ISS-2026-00926 phase 2)."""

from __future__ import annotations

import frappe
from frappe import _

from dinext_timesheets.timesheet_status import POSITION_EDITING

from ..permissions import (
	assert_can_edit_timesheet,
	has_worker_scope,
	timesheet_management_transitions,
	worker_group,
)
from .hours import calculate_utp_all_hours
from .limits_notify import notify_task_limit_exceeded
from .ownership import set_utp_owner_from_user, set_utp_period, set_utp_user_group
from .status_rollup import rollup_ut_status_and_task_dates
from .utilization import apply_utilization_hours
from .workflow_tasks import (
	delete_linked_workflow_tasks,
	process_workflow_tasks_after_save,
	process_workflow_tasks_before_save,
)


def before_insert(doc, method=None):
	if not doc.flags.ignore_permissions:
		parent = frappe.get_doc("User Timesheet", doc.user_timesheet)
		assert_can_edit_timesheet(parent)
		if doc.user and doc.user != parent.timesheet_from:
			frappe.throw(_("The position must belong to the timesheet worker"), frappe.PermissionError)
		if doc.status and doc.status != POSITION_EDITING:
			frappe.throw(_("A new position must be in editing"), frappe.PermissionError)
		doc.user = parent.timesheet_from
		doc.status = POSITION_EDITING
		doc.user_group = worker_group(parent.timesheet_from)
	set_utp_owner_from_user(doc)
	set_utp_period(doc)


def before_save(doc, method=None):
	before = doc.get_doc_before_save()
	if before and not doc.flags.ignore_permissions:
		if any(doc.get(key) != before.get(key) for key in ("user_timesheet", "user", "user_group")):
			frappe.throw(_("The position must belong to the timesheet worker"), frappe.PermissionError)
		if doc.workflow_state == before.workflow_state:
			if doc.status != before.status:
				frappe.throw(_("Change the position status through its Workflow"), frappe.PermissionError)
			assert_can_edit_timesheet(frappe.get_doc("User Timesheet", doc.user_timesheet))
		elif any(row.next_state == doc.workflow_state for row in timesheet_management_transitions(before)):
			parent = frappe.get_doc("User Timesheet", doc.user_timesheet)
			if not has_worker_scope(parent.timesheet_from, parent.ts_valid_for) or not frappe.has_permission(
				before, "write", ignore_share_permissions=True
			):
				frappe.throw(_("Not permitted to edit this timesheet"), frappe.PermissionError)
	# Block B WT before ownership/hours (status may change via workflow).
	process_workflow_tasks_before_save(doc)
	set_utp_user_group(doc)
	apply_utilization_hours(doc)
	calculate_utp_all_hours(doc)


def on_update(doc, method=None):
	# Demodev SS event label "After Save" → Document.on_update
	process_workflow_tasks_after_save(doc)
	rollup_ut_status_and_task_dates(doc)
	notify_task_limit_exceeded(doc)


def on_trash(doc, method=None):
	if not doc.flags.ignore_permissions:
		assert_can_edit_timesheet(frappe.get_doc("User Timesheet", doc.user_timesheet))
	# Demodev SS: Before Delete → Frappe hook on_trash
	delete_linked_workflow_tasks(doc)
