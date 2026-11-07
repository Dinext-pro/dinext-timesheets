"""Owned data for compact position-list acceptance against real Desk APIs."""

from __future__ import annotations

import frappe
from dinext_common.tests.ui_test_helpers import (
	PASSWORD,
	_engine_paused,
	_ensure_permission_condition,
	_ensure_read_perm,
	_ensure_role,
	_ensure_user,
	_manual_task,
	_transition,
)
from frappe.tests.ui_test_helpers import whitelist_for_tests

from dinext_timesheets.tests.ui_test_helpers import _worker

PREFIX = "_Cypress UTP List"
ROLE = PREFIX + " Reader"
OWNER = "cy.utp.list.owner@example.com"
APPROVER = "cy.utp.list.approver@example.com"
VIEWER = "cy.utp.list.viewer@example.com"
USERS = (OWNER, APPROVER, VIEWER)
GROUP = PREFIX + " Group"
WORKFLOW = PREFIX + " Workflow"
PROJECT = PREFIX + " Project"
PROJECT_ROLE = PREFIX + " Project Role"
ACTION = PREFIX + " Approve"


@whitelist_for_tests
def cleanup_utp_list():
	timesheets = frappe.get_all("User Timesheet", filters={"timesheet_from": OWNER}, pluck="name")
	positions = (
		frappe.get_all(
			"User Timesheet Position", filters={"user_timesheet": ("in", timesheets)}, pluck="name"
		)
		if timesheets
		else []
	)
	previous = frappe.flags.get("in_workflow_task_retention")
	frappe.flags.in_workflow_task_retention = True
	try:
		if positions:
			for name in frappe.get_all(
				"Workflow Task",
				filters={"reference_doctype": "User Timesheet Position", "reference_name": ("in", positions)},
				pluck="name",
			):
				frappe.delete_doc("Workflow Task", name, force=True, ignore_permissions=True)
		with _engine_paused():
			for name in positions:
				frappe.delete_doc("User Timesheet Position", name, force=True, ignore_permissions=True)
			for name in timesheets:
				frappe.delete_doc("User Timesheet", name, force=True, ignore_permissions=True)
	finally:
		frappe.flags.in_workflow_task_retention = previous
	for name in frappe.get_all("Issue", filters={"name": ("like", PREFIX + " Issue %")}, pluck="name"):
		frappe.delete_doc("Issue", name, force=True, ignore_permissions=True)
	for doctype, name in (
		("Project", PROJECT),
		("Project Role", PROJECT_ROLE),
		("Workflow", WORKFLOW),
		("Workflow Action Master", ACTION),
	):
		if frappe.db.exists(doctype, name):
			frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
	for name in frappe.get_all("Worker", filters={"wuser": ("in", USERS)}, pluck="name"):
		frappe.delete_doc("Worker", name, force=True, ignore_permissions=True)
	if frappe.db.exists("User Group", GROUP):
		frappe.delete_doc("User Group", GROUP, force=True, ignore_permissions=True)
	for user in USERS:
		if frappe.db.exists("User", user):
			frappe.delete_doc("User", user, force=True, ignore_permissions=True)
	frappe.db.delete("Custom DocPerm", {"role": ROLE})
	frappe.db.delete("DocType Permission Condition", {"role": ROLE})
	if frappe.db.exists("Role", ROLE):
		frappe.delete_doc("Role", ROLE, force=True, ignore_permissions=True)
	frappe.clear_cache()
	return {"cleaned": True}


@whitelist_for_tests
def seed_utp_list():
	cleanup_utp_list()
	if not frappe.conf.get("enable_parallel_workflow_approval"):
		frappe.throw("Parallel workflow approval is required for this fixture")
	_ensure_role(ROLE)
	for doctype in (
		"User Timesheet",
		"User Timesheet Position",
		"Issue",
		"Project",
		"Project Role",
		"Kanban Board",
		"Report",
		"Support Settings",
	):
		_ensure_read_perm(doctype, ROLE)
	for parent in (
		"UT_Permissions-1",
		"UTP_Permissions-1",
		"Issue_Permissions",
		"Project_Permissions",
		"Project_Permissions-1",
	):
		_ensure_permission_condition(parent, ROLE)
	for email, title in (
		(OWNER, "Cypress List Owner"),
		(APPROVER, "Cypress List Approver"),
		(VIEWER, "Cypress List Viewer"),
	):
		_ensure_user(email, title, [ROLE, "Desk User", "System Manager", "Dinext_Worker"])
	calendar = _worker()
	start, end = calendar.period
	frappe.get_doc({"doctype": "User Group", "name": GROUP, "user_group_members": [{"user": OWNER}]}).insert(
		ignore_permissions=True
	)
	frappe.get_doc(
		{
			"doctype": "Worker",
			"wuser": OWNER,
			"wfullname": "Cypress List Owner",
			"wuser_group": GROUP,
			"wvalid_from": start,
			"wtimesheet_template": calendar.wtimesheet_template,
			"wholiday_list": calendar.wholiday_list,
		}
	).insert(ignore_permissions=True)
	# These are owned display references; insertion avoids unrelated project provisioning.
	frappe.get_doc(
		{"doctype": "Project", "name": PROJECT, "project_name": "Cypress List Project", "status": "Open"}
	).db_insert()
	frappe.get_doc({"doctype": "Project Role", "name": PROJECT_ROLE}).db_insert()
	transition = _transition(ACTION, "Approved", policy="Any", uuid="cypress-utp-list-approve", allowed=ROLE)
	transition["state"] = "Pending Approval"
	frappe.get_doc(
		{
			"doctype": "Workflow",
			"workflow_name": WORKFLOW,
			"document_type": "User Timesheet Position",
			"workflow_state_field": "workflow_state",
			"is_active": 0,
			"states": [
				{"state": state, "doc_status": "0", "allow_edit": "All"}
				for state in ("Pending Approval", "Approved")
			],
			"transitions": [transition],
		}
	).insert(ignore_permissions=True)
	positions = []
	with _engine_paused():
		parent = frappe.get_doc(
			{
				"doctype": "User Timesheet",
				"timesheet_from": OWNER,
				"timesheet_from_name": "Cypress List Owner",
				"ts_valid_from": start,
				"ts_valid_for": end,
				"ut_status": "Draft",
			}
		).insert(ignore_permissions=True)
		for index in range(21):
			issue = frappe.get_doc(
				{
					"doctype": "Issue",
					"name": PREFIX + f" Issue {index:02}",
					"subject": f"Cypress List Document {index:02}",
					"status": "Open",
					"project": PROJECT,
				}
			)
			issue.db_insert()
			position = frappe.get_doc(
				{
					"doctype": "User Timesheet Position",
					"user_timesheet": parent.name,
					"user": OWNER,
					"workflow_state": "Editing",
					"status": "Editing",
				}
			).insert(ignore_permissions=True)
			state = "Approved" if index == 0 else "Pending Approval"
			values = {
				"custom_username": "Cypress List Owner",
				"status": state,
				"workflow_state": state,
				"period": str(start),
				"project": PROJECT,
				"project_role": PROJECT_ROLE,
				"document_type": "Issue",
				"document_name": issue.name,
				"all_hours": index + 1,
			}
			if frappe.get_meta("User Timesheet Position").has_field("document_subject"):
				values["document_subject"] = issue.subject
			frappe.db.set_value("User Timesheet Position", position.name, values, update_modified=False)
			task = None
			if state == "Pending Approval":
				task = _manual_task(
					doctype="User Timesheet Position",
					name=position.name,
					workflow=WORKFLOW,
					state=state,
					approver=APPROVER,
					round_status="Open",
					status="Working",
					round_id=frappe.generate_hash(length=40),
					action=ACTION,
					next_state="Approved",
					transition_uuid="cypress-utp-list-approve",
					allowed_role=ROLE,
				)
			positions.append(
				{"name": position.name, "task": task, "document": issue.subject, "hours": index + 1}
			)
	frappe.clear_cache()
	return {
		"timesheet": parent.name,
		"positions": positions,
		"owner": OWNER,
		"owner_name": "Cypress List Owner",
		"approver": APPROVER,
		"viewer": VIEWER,
		"password": PASSWORD,
		"project": PROJECT,
		"project_title": "Cypress List Project",
		"project_role": PROJECT_ROLE,
		"period": str(start),
	}
