"""Disposable Timesheet and Position fixtures for destination styles."""

import frappe
from frappe.tests.ui_test_helpers import whitelist_for_tests

from dinext_common.tests.ui_test_helpers import _delete_tasks_for
from dinext_common.tests.workflow_style_ui import _guard, _master, _task

PREFIX = "Cypress Timesheet Style "
ACTIONS = ((PREFIX + "Approve", "Approved"), (PREFIX + "Reject", "Rejected"))


@whitelist_for_tests(methods=["POST"])
def cleanup_workflow_styles():
	_guard()
	previous = frappe.flags.in_workflow_task_retention
	try:
		_delete_tasks_for("User Timesheet Position", [PREFIX + "Position"])
	finally:
		frappe.flags.in_workflow_task_retention = previous
	for doctype, name in (
		("User Timesheet Position", PREFIX + "Position"),
		("User Timesheet", PREFIX + "Timesheet"),
		("Workflow", PREFIX + "Positions"),
	):
		frappe.delete_doc_if_exists(doctype, name, force=True)
	for action, _ in ACTIONS:
		frappe.delete_doc_if_exists("Workflow Action Master", action, force=True)
	frappe.clear_cache()


@whitelist_for_tests(methods=["POST"])
def seed_workflow_styles():
	_guard()
	cleanup_workflow_styles()
	for (action, state), icon, style in zip(ACTIONS, ("check", "close"), ("Success", "Danger"), strict=True):
		_master("Workflow Action Master", action, workflow_action_name=action, custom_icon=icon)
		_master("Workflow State", state, workflow_state_name=state, style=style)
	parent = frappe.get_doc(
		{
			"doctype": "User Timesheet",
			"name": PREFIX + "Timesheet",
			"timesheet_from": "Guest",
			"timesheet_from_name": "Workflow style test",
			"ts_valid_from": "2039-01-03",
			"ts_valid_for": "2039-01-09",
			"ut_status": "Pending Approval",
		}
	)
	parent.db_insert()
	position = frappe.get_doc(
		{
			"doctype": "User Timesheet Position",
			"name": PREFIX + "Position",
			"user_timesheet": parent.name,
			"user": "Guest",
			"status": "Pending Approval",
			"all_hours": 8.0,
			"period": "2039-01",
		}
	)
	position.db_insert()
	position.append(
		"table", {"date": "2039-01-03", "hours": 8.0, "description": "Style test", "utilized_hours": 8.0}
	).db_insert()
	utp_workflow = frappe.get_doc(
		{
			"doctype": "Workflow",
			"workflow_name": PREFIX + "Positions",
			"document_type": position.doctype,
			"workflow_state_field": "status",
			"custom_activation_condition": f"doc.name == {position.name!r}",
			"is_active": 1,
			"send_email_alert": 0,
			"states": [
				{"state": state, "doc_status": "0", "allow_edit": "System Manager"}
				for state in ("Pending Approval", "Approved", "Rejected")
			],
			"transitions": [
				{
					"state": "Pending Approval",
					"action": action,
					"next_state": target,
					"allowed": "System Manager",
					"allow_self_approval": 1,
				}
				for action, target in ACTIONS
			],
		}
	).insert(ignore_permissions=True)
	frappe.clear_cache(doctype=position.doctype)
	_task(position, utp_workflow, utp_workflow.transitions, "position", prefix=PREFIX)
	return {"timesheet": parent.name, "position": position.name}
