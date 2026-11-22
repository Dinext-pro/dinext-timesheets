"""Scenario behavior at the timesheet position document hooks."""

from __future__ import annotations

import frappe
from frappe import _


def before_position_save(original, doc, method=None):
	from dinext_common.workflow_approval.scenarios import compat, service
	from dinext_timesheets.dinext_timesheets.user_timesheet.permissions import (
		has_worker_scope,
		timesheet_management_transitions,
	)

	before = doc.get_doc_before_save()
	if not before or doc.flags.ignore_permissions or not compat.is_authorized_finalization(doc):
		return original(doc, method)
	field = service.get_context(doc).get("state_field")
	if not field or field == "workflow_state" or before.get(field) == doc.get(field):
		return original(doc, method)
	if any(doc.get(key) != before.get(key) for key in ("user_timesheet", "user", "user_group")):
		frappe.throw(_("The position must belong to the timesheet worker"), frappe.PermissionError)
	if any(row.next_state == doc.get(field) for row in timesheet_management_transitions(before)):
		parent = frappe.get_doc("User Timesheet", doc.user_timesheet)
		if not has_worker_scope(parent.timesheet_from, parent.ts_valid_for) or not frappe.has_permission(
			before, "write", ignore_share_permissions=True
		):
			frappe.throw(_("Not permitted to edit this timesheet"), frappe.PermissionError)
	# Keep the producer's position processing while substituting the selected field for its legacy gate.
	previous = doc.flags.ignore_permissions
	doc.flags.ignore_permissions = True
	try:
		return original(doc, method)
	finally:
		doc.flags.ignore_permissions = previous


def handle_selected_state_update(doc) -> bool:
	"""Roll up selected state changes that did not change the legacy domain status."""
	from dinext_common.workflow_approval.scenarios import service
	from dinext_timesheets import workflow_approval

	if not workflow_approval._enabled():
		return False
	field = service.get_context(doc).get("state_field")
	before = doc.get_doc_before_save()
	if not field or field == "status" or not before or before.status != doc.status:
		return False
	if before.get(field) == doc.get(field):
		return False
	if not (frappe.flags.defer_timesheet_rollup or frappe.flags.in_timesheet_approval_cascade):
		parent = frappe.get_doc("User Timesheet", doc.user_timesheet, for_update=True)
		workflow_approval._recalculate_parent(parent, doc, before.status)
	return True


def task_no_longer_matches_source(task_name: str) -> bool:
	from dinext_common.workflow_approval.scenarios import service

	task = frappe.db.get_value(
		"Workflow Task", task_name,
		["status", "round_status", "reference_doctype", "reference_name", "workflow", "workflow_process", "workflow_state", "source_created_at"],
		as_dict=True,
	)
	if not task or task.status != "Working" or task.round_status != "Open":
		return True
	try:
		source = frappe.get_doc(task.reference_doctype, task.reference_name)
	except frappe.DoesNotExistError:
		return True
	if task.source_created_at and str(task.source_created_at) != str(source.creation):
		from frappe.utils import get_datetime

		if get_datetime(task.source_created_at) != get_datetime(source.creation):
			return True
	context = service.get_context(source)
	return (
		not context.get("workflow")
		or context.get("workflow") != task.workflow
		or context.get("process_id") != (task.workflow_process or None)
		or str(context.get("state") or "") != str(task.workflow_state or "")
	)
