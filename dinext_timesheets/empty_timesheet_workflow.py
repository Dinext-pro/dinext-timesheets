"""Workflow actions for a saved timesheet with no positions."""

from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

from dinext_timesheets import workflow_approval
from dinext_timesheets.dinext_timesheets.user_timesheet.permissions import has_worker_scope
from dinext_timesheets.timesheet_status import (
	APPROVED_TIMESHEET_STATUSES,
	PARENT_APPROVED,
	PARENT_DRAFT,
	PARENT_REWORK,
)

SCOPE = "timesheet"
APPROVE = "Approve"
RETURN_TO_EDITING = "Return to Editing"
EDITABLE_STATUSES = {PARENT_DRAFT, PARENT_REWORK}


def has_positions(timesheet_name, *, for_update=False):
	return bool(frappe.db.get_value(
		"User Timesheet Position", {"user_timesheet": timesheet_name}, "name",
		for_update=for_update,
	))


def guard_status_write(doc):
	if doc.flags.ignore_permissions:
		return
	before = doc.get_doc_before_save()
	was_approved = bool(before and before.ut_status in APPROVED_TIMESHEET_STATUSES)
	is_approved = doc.ut_status in APPROVED_TIMESHEET_STATUSES
	if was_approved != is_approved and not has_positions(doc.name, for_update=True):
		raise frappe.PermissionError(_("Use Workflow to change the approval status of an empty timesheet"))


def _can_manage(parent):
	return has_worker_scope(parent.timesheet_from, parent.ts_valid_from)


def _validate_approval(parent):
	errors = workflow_approval._validate_parent_period(parent)
	if not errors:
		template, holidays, reduced, leave_hours = workflow_approval._calendar_context(parent)
		standard = flt(template.hours_on_date)
		day = getdate(parent.ts_valid_from)
		end = getdate(parent.ts_valid_for)
		while day <= end:
			if day not in holidays and (
				day not in leave_hours or leave_hours[day] < reduced.get(day, standard)
			):
				errors.append(_("{0}: Approved absence does not cover the full workday").format(day))
			day += timedelta(days=1)
		errors.extend(workflow_approval._validate_daily_totals(
			parent, [], template, holidays, reduced, leave_hours,
		))
	if errors:
		raise frappe.ValidationError(_("Timesheet filling errors") + ": " + " ".join(errors))


def get_actions(timesheet_name):
	parent = frappe.get_doc("User Timesheet", timesheet_name)
	parent.check_permission("read")
	if not _can_manage(parent):
		return []
	if parent.ut_status in APPROVED_TIMESHEET_STATUSES:
		action = RETURN_TO_EDITING
	elif parent.ut_status in EDITABLE_STATUSES:
		try:
			_validate_approval(parent)
		except frappe.ValidationError:
			return []
		action = APPROVE
	else:
		return []
	return [{
		"scope": SCOPE,
		"action": action,
		"positions": [],
		"comment_is_required": False,
		"confirm_return_to_editing": action == RETURN_TO_EDITING,
		"runs_timesheet_checks": action == APPROVE,
	}]


def apply_action(timesheet_name, action, request_id=None):
	from dinext_common.workflow_approval import request_receipts
	from dinext_timesheets.workflow_scenario_actions import atomic_timesheet_transition

	parent = frappe.get_doc("User Timesheet", timesheet_name, for_update=True)
	parent.check_permission("read")
	if not _can_manage(parent):
		raise frappe.PermissionError(_("You are not allowed to manage this timesheet"))

	parameters = [request_receipts.target(parent), action]
	with atomic_timesheet_transition(also_rollback=(Exception,)):
		receipt = None
		if request_id:
			receipt = request_receipts.reserve("Empty Timesheet", request_id, parameters, [parameters[0]])
			if receipt.response is not None:
				return request_receipts.replay(receipt, parameters)

		if has_positions(parent.name, for_update=True):
			raise frappe.ValidationError(_("This action is only available for a timesheet without positions"))
		if action == APPROVE and parent.ut_status in EDITABLE_STATUSES:
			_validate_approval(parent)
			parent.ut_status = PARENT_APPROVED
			parent.ut_approval_date = nowdate()
		elif action == RETURN_TO_EDITING and parent.ut_status in APPROVED_TIMESHEET_STATUSES:
			parent.ut_status = PARENT_REWORK
			parent.ut_approval_date = None
		else:
			raise frappe.ValidationError(_("The action is not available for the current timesheet status"))

		parent.save(ignore_permissions=True)
		response = {
			"timesheet": parent.name,
			"results": [{"name": parent.name, "transitioned": True}],
			"messages": [],
			"processed": 1,
			"total": 1,
		}
		if receipt:
			request_receipts.finish(receipt.name, response)
		return response
