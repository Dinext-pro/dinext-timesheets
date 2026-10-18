"""Notify project team when UTP enters approval with limit overrun (phase 2 C).

Port of demodev Server Script ``Task Limit Exceeded_V4`` (After Save / on_update).
Calculate via PWA ``project_workload_assignment.api.calculate_user_timesheet_limits``
(ISS-2026-02105 unified calculator; same core as ``calculate_timesheet_limits``).
"""

from __future__ import annotations

import json

import frappe
from frappe.utils.safe_exec import call_whitelisted_function

LIMITS_METHOD = "project_workload_assignment.api.calculate_user_timesheet_limits"


def notify_task_limit_exceeded(doc) -> None:
	old_doc = doc.get_doc_before_save()
	if not old_doc:
		return

	from dinext_timesheets.timesheet_status import PENDING_POSITION_STATUSES

	entered_pending = (
		old_doc.status not in PENDING_POSITION_STATUSES
		and doc.status in PENDING_POSITION_STATUSES
	)
	if not entered_pending:
		return

	project_managers = frappe.db.get_all(
		"Project Team Details",
		filters={"parent": doc.project, "notifications_on_limits": 1},
		fields=["pt_participant"],
	)
	if not project_managers:
		return

	position_data = {
		"document_name": doc.document_name,
		"project_role": doc.project_role,
		"project": doc.project,
		"status": doc.status,
	}

	api_result = call_whitelisted_function(
		LIMITS_METHOD,
		positions=json.dumps([position_data]),
		timesheet_name=doc.name,
	)
	# SS read frappe.response.message; whitelisted method returns value directly.
	if api_result is None:
		api_result = frappe.response.get("message")

	if not api_result:
		return

	result = api_result[0]
	if not result.get("planned_hours", 0) > 0:
		return

	notification_limit = frappe.db.get_value(
		"Limit Control",
		{"parent": doc.project, "type": "Уведомление", "view": "Notification"},
		["limit", "notification"],
		as_dict=True,
	)
	if not notification_limit:
		return

	completion_percentage = (result["total_hours"] / result["planned_hours"]) * 100
	if completion_percentage <= notification_limit.limit:
		return

	context = {
		"completion_percentage": completion_percentage,
		"actual_hours": result["total_hours"],
		"planned_hours": result["planned_hours"],
		"timesheet_position": doc.name,
		"task_name": doc.document_name,
		"project": doc.project,
		"project_role": doc.project_role,
	}

	notification = frappe.get_doc(
		"Notification", notification_limit.notification, ignore_permissions=True
	)

	for manager in project_managers:
		todo = frappe.new_doc("ToDo")
		todo.description = "Уведомление о превышении лимитов"
		todo.allocated_to = manager.pt_participant
		todo.reference_type = "User Timesheet Position"
		todo.reference_name = doc.name
		todo.flags.context = context
		notification.send(todo)
