"""User Timesheet Position doc_events (ISS-2026-00926 phase 2)."""

from __future__ import annotations

import frappe
from frappe import _

from dinext_timesheets.empty_timesheet_workflow import has_positions
from dinext_timesheets.timesheet_status import APPROVED_TIMESHEET_STATUSES, POSITION_EDITING

from ..permissions import (
	assert_can_edit_timesheet,
	has_worker_scope,
	is_timesheet_management_state_change,
	worker_group,
)
from ..status import has_legacy_position_status
from .hours import calculate_utp_all_hours
from .limits_notify import notify_task_limit_exceeded
from .ownership import set_utp_owner_from_user, set_utp_period, set_utp_user_group
from .status_rollup import rollup_ut_status_and_task_dates
from .utilization import apply_utilization_hours
from .workflow_tasks import sync_status_from_workflow_state


def before_insert(doc, method=None):
	parent = frappe.get_doc("User Timesheet", doc.user_timesheet, for_update=True)
	if parent.ut_status in APPROVED_TIMESHEET_STATUSES and not has_positions(parent.name, for_update=True):
		frappe.throw(_("Return the empty timesheet to editing before adding positions"))
	if not doc.flags.ignore_permissions:
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
	from dinext_timesheets.workflow_scenario_actions import uses_local_scenarios

	if uses_local_scenarios():
		from dinext_timesheets.workflow_scenario_positions import before_position_save

		return before_position_save(_before_save, doc, method)
	return _before_save(doc, method)


def _before_save(doc, method=None):
	before = doc.get_doc_before_save()
	if before and not doc.flags.ignore_permissions:
		if any(doc.get(key) != before.get(key) for key in ("user_timesheet", "user", "user_group")):
			frappe.throw(_("The position must belong to the timesheet worker"), frappe.PermissionError)
		state_field = "workflow_state" if has_legacy_position_status() else "status"
		if doc.get(state_field) == before.get(state_field):
			if doc.status != before.status:
				frappe.throw(_("Change the position status through its Workflow"), frappe.PermissionError)
			assert_can_edit_timesheet(frappe.get_doc("User Timesheet", doc.user_timesheet))
		elif is_timesheet_management_state_change(before, doc, state_field):
			parent = frappe.get_doc("User Timesheet", doc.user_timesheet)
			if not has_worker_scope(parent.timesheet_from, parent.ts_valid_for) or not frappe.has_permission(
				before, "write", ignore_share_permissions=True
			):
				frappe.throw(_("Not permitted to edit this timesheet"), frappe.PermissionError)
	sync_status_from_workflow_state(doc)
	set_utp_user_group(doc)
	apply_utilization_hours(doc)
	calculate_utp_all_hours(doc)


def on_update(doc, method=None):
	rollup_ut_status_and_task_dates(doc)
	notify_task_limit_exceeded(doc)


def on_trash(doc, method=None):
	if not doc.flags.ignore_permissions:
		assert_can_edit_timesheet(frappe.get_doc("User Timesheet", doc.user_timesheet))
