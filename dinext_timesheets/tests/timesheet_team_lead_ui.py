"""Isolated Desk data for the delegated timesheet scenario."""

from __future__ import annotations

from textwrap import indent

import frappe
from frappe.model.workflow import get_workflow
from frappe.tests.ui_test_helpers import whitelist_for_tests
from frappe.utils.password import update_password

PREFIX = "Cypress UT Team Lead"
WORKER = "cy.ut.team.worker@example.com"
LEAD = "cy.ut.team.lead@example.com"
FORMER = "cy.ut.team.former@example.com"
APPROVER = "cy.ut.team.approver@example.com"
START = "2039-01-03"
END = "2039-01-09"
FIXTURE_SETTINGS = "timesheet_team_lead_ui_original_settings"


def _insert(doctype, name, **fields):
	doc = frappe.get_doc({"doctype": doctype, "name": name, **fields})
	doc.db_insert()
	return doc


def _restore_fixture_settings():
	backup = frappe.cache.get_value(FIXTURE_SETTINGS)
	if not backup:
		return
	for name, condition in backup["conditions"].items():
		frappe.db.set_value("Workflow Transition", name, "condition", condition, update_modified=False)
	frappe.clear_document_cache("Workflow", backup["workflow"])
	for name, script in backup["scripts"].items():
		frappe.db.set_value("Server Script", name, "script", script, update_modified=False)
		frappe.clear_document_cache("Server Script", name)
	frappe.cache.delete_value(FIXTURE_SETTINGS)


def _scope_fixture_settings(workflow, project, transitions):
	# Keep the site's approval quorum and isolate the synthetic project's voters.
	scripts = frappe.get_all(
		"Server Script",
		filters={"api_method": ("in", [
			"create_journal_entries_for_approved_timesheet",
			"cancelled_journal_entries_for_rejected_timesheet.process_rejected_timesheet",
		]), "disabled": 0},
		fields=["name", "api_method", "script"],
	)
	if getattr(frappe.local, "request", None):
		frappe.cache.set_value(FIXTURE_SETTINGS, {
			"workflow": workflow.name,
			"conditions": {row.name: row.condition for row in transitions},
			"scripts": {row.name: row.script for row in scripts},
		})
	for row in transitions:
		condition = f"({row.condition or 'True'}) and (doc.project != {project!r} or frappe.session.user == {APPROVER!r})"
		frappe.db.set_value(row.doctype, row.name, "condition", condition, update_modified=False)
	frappe.clear_document_cache("Workflow", workflow.name)

	# The synthetic Worker has no accounts or cost rates. Exercise workflow without posting.
	for row in scripts:
		worker = (
			'frappe.form_dict.doc.get("timesheet_from")'
			if row.api_method == "create_journal_entries_for_approved_timesheet"
			else 'frappe.db.get_value("User Timesheet", frappe.form_dict.user_timesheet_name, "timesheet_from")'
		)
		script = f"if {worker} != {WORKER!r}:\n" + indent(row.script, "\t")
		frappe.db.set_value("Server Script", row.name, "script", script, update_modified=False)
		frappe.clear_document_cache("Server Script", row.name)


def _remove_position(position):
	names = frappe.get_all("Workflow Task", filters={
		"reference_doctype": "User Timesheet Position", "reference_name": position,
	}, pluck="name")
	previous = frappe.flags.in_workflow_task_retention
	frappe.flags.in_workflow_task_retention = True
	try:
		for name in names:
			frappe.delete_doc("Workflow Task", name, ignore_permissions=True, force=True)
	finally:
		frappe.flags.in_workflow_task_retention = previous
	frappe.delete_doc("User Timesheet Position", position, ignore_permissions=True, force=True)


@whitelist_for_tests
def cleanup():
	if not frappe.has_permission("Workflow", "write"):
		raise frappe.PermissionError
	_restore_fixture_settings()
	names = frappe.get_all("User Timesheet", filters={"timesheet_from": WORKER}, pluck="name")
	for name in names:
		positions = frappe.get_all(
			"User Timesheet Position", filters={"user_timesheet": name}, pluck="name"
		)
		for position in positions:
			_remove_position(position)
		frappe.delete_doc("User Timesheet", name, ignore_permissions=True, force=True)
	for doctype, field in (
		("DocShare", "share_name"),
		("Project Team Details", "parent"),
		("Task", "name"),
		("Project", "name"),
		("Project Role", "name"),
		("Doctype for Timesheet", "parent"),
		("Worker", "name"),
		("Timesheet Template", "name"),
		("Holiday List", "name"),
		("Teamleads Table", "parent"),
		("User Group Member", "parent"),
		("User Group", "name"),
	):
		frappe.db.delete(doctype, {field: ("like", f"{PREFIX}%")})
	for email in (WORKER, LEAD, FORMER, APPROVER):
		if frappe.db.exists("User", email):
			frappe.delete_doc("User", email, ignore_permissions=True, force=True)
	return True


@whitelist_for_tests
def seed():
	cleanup()
	workflow = get_workflow("User Timesheet Position")
	transitions = {(row.state, row.next_state): row for row in workflow.transitions}
	basic_role = transitions["Editing", "Pending Approval"].allowed
	lead_role = frappe.db.get_value("Custom DocPerm", "ut-team-lead-access", "role")
	approver_role = transitions["Pending Approval", "Rejected"].allowed
	password = frappe.generate_hash(length=24)
	for email, roles in (
		(WORKER, [basic_role]),
		(LEAD, [basic_role, lead_role]),
		(FORMER, [basic_role, lead_role]),
		(APPROVER, [basic_role, approver_role]),
	):
		user = frappe.get_doc({
			"doctype": "User", "email": email, "first_name": f"{PREFIX} {email.split('@')[0].rsplit('.', 1)[-1]}",
			"enabled": 1, "send_welcome_email": 0, "user_type": "System User", "language": "en",
			"roles": [{"role": role} for role in set(roles)],
		}).insert(ignore_permissions=True)
		update_password(user.name, password)

	group = PREFIX + " Group"
	_insert("User Group", group)
	for idx, (lead, date) in enumerate(((FORMER, START), (FORMER, END), (LEAD, END)), start=1):
		_insert(
			"Teamleads Table", f"{PREFIX} Assignment {idx}", parent=group, parenttype="User Group",
			parentfield="custom_table", date=date, idx=idx, teamlead=lead,
		)
	calendar = PREFIX + " Calendar"
	template = PREFIX + " Template"
	_insert("Holiday List", calendar, holiday_list_name=calendar, from_date=START, to_date=END)
	_insert("Timesheet Template", template, ttsubject=template, ttreporting_period="Недельный",
		hours_on_date=0, minimum_hours=0, maximum_hours=24, enabled=1)
	_insert("Doctype for Timesheet", PREFIX + " Type", parent=template,
		parenttype="Timesheet Template", parentfield="doctype_for_timesheet", dtdoctype="Task")
	_insert(
		"Worker", PREFIX + " Worker", wuser=WORKER, wfullname=PREFIX + " Worker", wuser_group=group,
		wvalid_from=START, wholiday_list=calendar, wtimesheet_template=template,
	)

	project = PREFIX + " Project"
	project_role = PREFIX + " Project Role"
	_scope_fixture_settings(workflow, project, [
		transitions["Pending Approval", "Rejected"], transitions["Pending Approval", "Approved"],
	])
	_insert("Project", project, project_name=project, status="Open", is_active="Yes",
		expected_start_date=START, expected_end_date=END)
	_insert("Project Role", project_role)
	for email in (WORKER, APPROVER):
		_insert(
			"Project Team Details", PREFIX + " Member " + email, parent=project, parenttype="Project",
			parentfield="custom_project_team", pt_participant_type="User", pt_participant=email,
			pt_role=project_role, pt_valid_from=START, pt_valid_for=END, allow_approval=int(email == APPROVER),
		)
	tasks = []
	for idx in (1, 2):
		task = f"{PREFIX} Task {idx}"
		tasks.append(task)
		_insert("Task", task, subject=task, project=project, status="Open",
			exp_start_date=START, exp_end_date=END, custom_include=1)
		_insert("DocShare", PREFIX + " Share " + str(idx), user=WORKER, share_doctype="Task",
			share_name=task, read=1)
	return {
		"worker": WORKER, "lead": LEAD, "former": FORMER, "approver": APPROVER,
		"password": password, "start": START, "end": END, "project": project, "role": project_role,
		"tasks": tasks, "actions": {
			"submit": transitions["Editing", "Pending Approval"].action,
			"withdraw": transitions["Pending Approval", "Editing"].action,
			"reject": transitions["Pending Approval", "Rejected"].action,
			"revise": transitions["Rejected", "Editing"].action,
			"approve": transitions["Pending Approval", "Approved"].action,
			"reopen": transitions["Approved", "Editing"].action,
		},
	}
