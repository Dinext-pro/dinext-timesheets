"""Dev-server fixture for the User Timesheet form Cypress spec.

Creates and deletes its own timesheet. Requires a Worker with a holiday list
already on the site. Methods refuse to run unless the process is a
development server (`DEV_SERVER=1`).
"""

from __future__ import annotations

from contextlib import contextmanager

import frappe
from frappe.tests.ui_test_helpers import whitelist_for_tests
from frappe.utils import add_days, date_diff, getdate

MARKER = "cypress-ut-form"
WORKFLOW_MARKER = "cypress-ut-workflow"


def _covered_period(worker):
	"""Seven days inside the worker's holiday list and working-hours calendar."""
	if not worker.wholiday_list or not worker.wtimesheet_template:
		return None
	holiday_list = frappe.db.get_value(
		"Holiday List",
		worker.wholiday_list,
		["from_date", "to_date"],
		as_dict=True,
	)
	template = frappe.db.get_value(
		"Timesheet Template",
		worker.wtimesheet_template,
		"tt_working_hours_on_date",
	)
	if not holiday_list or not holiday_list.from_date or not holiday_list.to_date:
		return None
	start = getdate(holiday_list.from_date)
	end = getdate(holiday_list.to_date)
	if template:
		hours = frappe.db.get_value(
			"Working Hours On Date",
			template,
			["hod_from_date", "hod_to_date"],
			as_dict=True,
		)
		if not hours or not hours.hod_from_date or not hours.hod_to_date:
			return None
		start = max(start, getdate(hours.hod_from_date))
		end = min(end, getdate(hours.hod_to_date))
	if date_diff(end, start) < 6:
		return None
	return start, add_days(start, 6)


def _worker():
	rows = frappe.get_all(
		"Worker",
		filters={
			"wholiday_list": ["!=", ""],
			"wuser": ["!=", ""],
			"wtimesheet_template": ["!=", ""],
		},
		fields=["name", "wuser", "wholiday_list", "wtimesheet_template"],
		limit=50,
	)
	for worker in rows:
		period = _covered_period(worker)
		if period:
			worker.period = period
			return worker
	frappe.throw("No Worker whose calendars cover a seven-day timesheet")


@whitelist_for_tests
def cleanup_ut_form_table():
	names = set(
		frappe.get_all(
			"User Timesheet",
			filters={"name": ["like", f"%{MARKER}%"]},
			pluck="name",
		)
	)
	names.update(
		frappe.get_all(
			"User Timesheet",
			filters={"timesheet_from_name": MARKER},
			pluck="name",
		)
	)
	for name in names:
		frappe.delete_doc(
			"User Timesheet",
			name,
			ignore_permissions=True,
			force=True,
		)
	return {"deleted": names}


@whitelist_for_tests
def seed_ut_form_table():
	cleanup_ut_form_table()
	worker = _worker()
	valid_from, valid_for = worker.period
	doc = frappe.get_doc(
		{
			"doctype": "User Timesheet",
			"timesheet_from": worker.wuser,
			"timesheet_from_name": MARKER,
			"ts_valid_from": valid_from,
			"ts_valid_for": valid_for,
			"ut_status": "Draft",
		}
	)
	doc.insert(ignore_permissions=True)
	return {"name": doc.name}


def _timesheet_names(marker):
	names = set(
		frappe.get_all(
			"User Timesheet",
			filters={"name": ["like", f"%{marker}%"]},
			pluck="name",
		)
	)
	names.update(
		frappe.get_all(
			"User Timesheet",
			filters={"timesheet_from_name": marker},
			pluck="name",
		)
	)
	return names


@contextmanager
def _pause_approval_engine():
	"""Skip round creation so an Editing position can exist without approvers."""
	from dinext_common.workflow_approval import lifecycle

	original = lifecycle._should_handle
	previous = frappe.flags.get("ut_workflow_fixture")
	frappe.flags.ut_workflow_fixture = True
	lifecycle._should_handle = lambda doc: (
		False if frappe.flags.get("ut_workflow_fixture") else original(doc)
	)
	try:
		yield
	finally:
		lifecycle._should_handle = original
		frappe.flags.ut_workflow_fixture = previous


def _delete_workflow_tasks(position_name):
	tasks = frappe.get_all(
		"Workflow Task",
		filters={
			"reference_doctype": "User Timesheet Position",
			"reference_name": position_name,
		},
		pluck="name",
	)
	previous = frappe.flags.get("in_workflow_task_retention")
	frappe.flags.in_workflow_task_retention = True
	try:
		for task_name in tasks:
			frappe.delete_doc(
				"Workflow Task", task_name, ignore_permissions=True, force=True,
			)
	finally:
		frappe.flags.in_workflow_task_retention = previous



@whitelist_for_tests
def cleanup_ut_workflow_button():
	names = _timesheet_names(WORKFLOW_MARKER)
	positions = []
	if names:
		positions = frappe.get_all(
			"User Timesheet Position",
			filters={"user_timesheet": ["in", list(names)]},
			pluck="name",
		)
	for position_name in positions:
		_delete_workflow_tasks(position_name)
		frappe.delete_doc(
			"User Timesheet Position",
			position_name,
			ignore_permissions=True,
			force=True,
		)
	for name in names:
		frappe.delete_doc(
			"User Timesheet",
			name,
			ignore_permissions=True,
			force=True,
		)
	return {"deleted": list(names), "positions": positions}


@whitelist_for_tests
def seed_ut_workflow_button():
	"""Saved timesheet whose owner can submit the Editing position."""
	cleanup_ut_workflow_button()
	worker = _worker()
	valid_from, valid_for = worker.period
	doc = frappe.get_doc(
		{
			"doctype": "User Timesheet",
			"timesheet_from": worker.wuser,
			"timesheet_from_name": WORKFLOW_MARKER,
			"ts_valid_from": valid_from,
			"ts_valid_for": valid_for,
			"ut_status": "Draft",
		}
	)
	doc.insert(ignore_permissions=True)
	position = frappe.get_doc(
		{
			"doctype": "User Timesheet Position",
			"user_timesheet": doc.name,
			"user": frappe.session.user,
			"status": "Editing",
		}
	)
	with _pause_approval_engine():
		position.insert(ignore_permissions=True)
	from dinext_timesheets.workflow_approval import get_timesheet_position_actions

	available = get_timesheet_position_actions(doc.name)
	actions = [row.get("action") for row in available.get("actions") or []]
	if not actions:
		frappe.throw("Seeded timesheet has no workflow action for the test user")
	return {"name": doc.name, "position": position.name, "actions": actions}


WORKFLOW_EVENT_USER = "cypress.ut.workflow@example.com"
WORKFLOW_EVENT_GROUP = "_Cypress UT Workflow Group"
WORKFLOW_EVENT_ROLE = "_Cypress UT Workflow Events"


@whitelist_for_tests
def cleanup_ut_workflow_stop():
	cleanup_ut_workflow_button()
	for name in frappe.get_all("Worker", filters={"wuser": WORKFLOW_EVENT_USER}, pluck="name"):
		frappe.delete_doc("Worker", name, ignore_permissions=True, force=True)
	if frappe.db.exists("User Group", WORKFLOW_EVENT_GROUP):
		frappe.delete_doc("User Group", WORKFLOW_EVENT_GROUP, ignore_permissions=True, force=True)
	if frappe.db.exists("User", WORKFLOW_EVENT_USER):
		frappe.delete_doc("User", WORKFLOW_EVENT_USER, ignore_permissions=True, force=True)
	frappe.db.delete("Custom DocPerm", {"role": WORKFLOW_EVENT_ROLE})
	if frappe.db.exists("Role", WORKFLOW_EVENT_ROLE):
		frappe.delete_doc("Role", WORKFLOW_EVENT_ROLE, ignore_permissions=True, force=True)


@whitelist_for_tests
def seed_ut_workflow_stop(position_count: int = 1, editing_only: int = 0, partially_rejected: int = 0):
	"""Own user and position using the installed stop/edit workflow, without changing it."""
	from dinext_timesheets.workflow_approval import get_timesheet_position_actions

	cleanup_ut_workflow_stop()
	fixture = _seed_ut_workflow_card(_worker(), 2 if partially_rejected else position_count)
	previous = frappe.session.user
	stop = None
	try:
		frappe.set_user(fixture["user"])
		editing = get_timesheet_position_actions(fixture["name"])["actions"]
		if not editing:
			frappe.throw("Seeded timesheet owner has no action in Editing")
		if not editing_only:
			for index, name in enumerate(fixture["positions"]):
				state = "Rejected" if partially_rejected and index == 1 else "Pending Approval"
				frappe.db.set_value("User Timesheet Position", name, {
					"status": state,
				}, update_modified=False)
			parent_status = "Rejected" if partially_rejected else "Pending Approval"
			frappe.db.set_value("User Timesheet", fixture["name"], "ut_status", parent_status, update_modified=False)
			pending = get_timesheet_position_actions(fixture["name"])["actions"]
			stop = next(
				(row for row in pending if all(p["next_state"] == "Editing" for p in row["positions"])),
				None,
			)
			if not stop:
				frappe.throw("Seeded timesheet owner has no action to return to Editing")
	finally:
		frappe.set_user(previous)
	return {**fixture, "stop_action": stop["action"] if stop else None,
		"editing_actions": [row["action"] for row in editing]}


def _seed_ut_workflow_card(calendar, position_count: int, *, name: str | None = None):
	from dinext_common.tests.ui_test_helpers import _ensure_read_perm
	from frappe.utils.password import update_password

	frappe.get_doc({"doctype": "Role", "role_name": WORKFLOW_EVENT_ROLE}).insert(ignore_permissions=True)
	for doctype in ("Kanban Board", "Report", "Support Settings"):
		_ensure_read_perm(doctype, WORKFLOW_EVENT_ROLE)
	start, end = calendar.period
	password = "cypress-ut-workflow-events"
	user = frappe.get_doc({
		"doctype": "User", "email": WORKFLOW_EVENT_USER,
		"first_name": WORKFLOW_MARKER, "enabled": 1, "send_welcome_email": 0,
		"user_type": "System User", "language": "ru",
		"roles": [{"role": "Dinext_Worker"}, {"role": "System Manager"}, {"role": WORKFLOW_EVENT_ROLE}],
	}).insert(ignore_permissions=True)
	update_password(user.name, password)
	frappe.clear_cache()
	frappe.get_doc({
		"doctype": "User Group", "name": WORKFLOW_EVENT_GROUP,
		"user_group_members": [{"user": user.name}],
	}).insert(ignore_permissions=True)
	frappe.get_doc({
		"doctype": "Worker", "wuser": user.name, "wfullname": WORKFLOW_MARKER,
		"wuser_group": WORKFLOW_EVENT_GROUP, "wvalid_from": start,
		"wtimesheet_template": calendar.wtimesheet_template,
		"wholiday_list": calendar.wholiday_list,
	}).insert(ignore_permissions=True)
	doc = frappe.get_doc({
		"doctype": "User Timesheet", "timesheet_from": user.name,
		"timesheet_from_name": WORKFLOW_MARKER,
		"ts_valid_from": start, "ts_valid_for": end, "ut_status": "Draft",
	}).insert(ignore_permissions=True, set_name=name)
	positions = []
	with _pause_approval_engine():
		for _index in range(position_count):
			position = frappe.get_doc({
				"doctype": "User Timesheet Position", "user_timesheet": doc.name,
				"user": user.name, "status": "Editing",
			}).insert(ignore_permissions=True)
			positions.append(position.name)
	return {"name": doc.name, "position": positions[0], "positions": positions, "user": user.name,
		"password": password}


BATCH_FAILURE_WORKFLOW = "_Cypress Timesheet Position Batch"
BATCH_FAILURE_ACTION = "_Cypress Review Positions"
BATCH_FAILURE_FOLLOW_UP = "_Cypress Review Again"
BATCH_FAILURE_PROJECT_ROLE = "Аналитик Cypress"


@whitelist_for_tests
def cleanup_ut_position_batch():
	cleanup_ut_workflow_stop()
	from dinext_common.workflow_approval.scenarios import service

	processes = frappe.get_all(service.PROCESS, filters={"workflow": BATCH_FAILURE_WORKFLOW},
		fields=["name", "source_key"])
	for process in processes:
		frappe.db.delete(service.CONTEXT, {"name": process.source_key})
		frappe.db.delete(service.PROCESS, {"name": process.name})
	frappe.delete_doc_if_exists("Workflow", BATCH_FAILURE_WORKFLOW, force=True)
	for action in (BATCH_FAILURE_ACTION, BATCH_FAILURE_FOLLOW_UP):
		frappe.delete_doc_if_exists("Workflow Action Master", action, force=True)
	for doctype in ("Timesheet Template", "Working Hours On Date", "Holiday List"):
		frappe.delete_doc_if_exists(doctype, BATCH_FAILURE_WORKFLOW, force=True)
	frappe.db.delete("Project Team Details", {"parent": BATCH_FAILURE_WORKFLOW})
	frappe.db.delete("Task", {"project": BATCH_FAILURE_WORKFLOW})
	frappe.db.delete("Project", {"name": BATCH_FAILURE_WORKFLOW})
	frappe.db.delete("Project Role", {"name": BATCH_FAILURE_PROJECT_ROLE})


def _position_batch_calendar():
	today = getdate()
	start = add_days(today, -today.weekday())
	end = add_days(start, 6)
	calendar = frappe.get_doc({
		"doctype": "Holiday List", "holiday_list_name": BATCH_FAILURE_WORKFLOW,
		"from_date": start, "to_date": add_days(end, 30),
	}).insert(ignore_permissions=True, set_name=BATCH_FAILURE_WORKFLOW)
	hours = frappe.get_doc({
		"doctype": "Working Hours On Date",
		"hod_from_date": start, "hod_to_date": end,
	}).insert(ignore_permissions=True, set_name=BATCH_FAILURE_WORKFLOW)
	template = frappe.get_doc({
		"doctype": "Timesheet Template", "ttsubject": BATCH_FAILURE_WORKFLOW,
		"enabled": 1, "ttreporting_period": "Недельный",
		"tt_working_hours_on_date": hours.name, "doctype_for_timesheet": [{"dtdoctype": "Task"}],
		"hours_on_date": 8, "minimum_hours": 0, "maximum_hours": 8, "working_days": 1,
	}).insert(ignore_permissions=True, set_name=BATCH_FAILURE_WORKFLOW)
	return frappe._dict(period=(start, end), wtimesheet_template=template.name, wholiday_list=calendar.name)


def _position_batch_labels(fixture, period):
	project = BATCH_FAILURE_WORKFLOW
	title = "Обновление портала"
	start, end = period
	frappe.get_doc({"doctype": "Project", "name": project, "project_name": title,
		"status": "Open", "is_active": "Yes"}).db_insert()
	frappe.get_doc({"doctype": "Project Role", "name": BATCH_FAILURE_PROJECT_ROLE}).db_insert()
	frappe.get_doc({"doctype": "Project Team Details", "name": project, "parent": project,
		"parenttype": "Project", "parentfield": "custom_project_team", "pt_participant_type": "User",
		"pt_participant": fixture["user"], "pt_role": BATCH_FAILURE_PROJECT_ROLE}).db_insert()
	subjects = []
	for index, position in enumerate(fixture["positions"], start=1):
		task = f"{project} Task {index}"
		subject = f"Настроить согласование {index}"
		frappe.get_doc({"doctype": "Task", "name": task, "subject": subject, "project": project,
			"status": "Open", "custom_include": 1, "exp_start_date": start, "exp_end_date": end}).db_insert()
		frappe.get_doc({"doctype": "DocShare", "name": task, "user": fixture["user"], "share_doctype": "Task",
			"share_name": task, "read": 1}).db_insert()
		frappe.db.set_value("User Timesheet Position", position, {
			"project": project, "document_type": "Task", "document_name": task,
			"project_role": BATCH_FAILURE_PROJECT_ROLE,
		})
		subjects.append(subject)
	return {"project": title, "tasks": subjects, "role": BATCH_FAILURE_PROJECT_ROLE}


@whitelist_for_tests
def seed_ut_position_batch(block_one: int = 1):
	"""Two positions with a real vote and an optional empty successor cohort."""
	from unittest.mock import patch

	from dinext_common.tests.ui_test_helpers import _ensure_read_perm
	from dinext_common.workflow_approval import engine
	from dinext_common.workflow_approval.scenarios import service
	from dinext_common.workflow_approval.scenarios.metadata import next_selection_order

	cleanup_ut_position_batch()
	calendar = _position_batch_calendar()
	fixture = _seed_ut_workflow_card(
		calendar, position_count=2, name=f"{WORKFLOW_MARKER}-{frappe.generate_hash(length=8)}"
	)
	labels = _position_batch_labels(fixture, calendar.period)
	for doctype in ("Workflow Task", "Comment"):
		_ensure_read_perm(doctype, WORKFLOW_EVENT_ROLE)
		frappe.clear_cache(doctype=doctype)
	position_doctype = "User Timesheet Position"
	for action in (BATCH_FAILURE_ACTION, BATCH_FAILURE_FOLLOW_UP):
		frappe.get_doc({"doctype": "Workflow Action Master", "workflow_action_name": action}).insert()
	workflow = frappe.get_doc({
		"doctype": "Workflow",
		"workflow_name": BATCH_FAILURE_WORKFLOW,
		"document_type": position_doctype,
		"workflow_state_field": "status",
		"custom_selection_order": next_selection_order(position_doctype),
		"custom_activation_condition": f"doc.user_timesheet == {fixture['name']!r}",
		"is_active": 1,
		"send_email_alert": 0,
		"states": [
			{"state": state, "doc_status": "0", "allow_edit": WORKFLOW_EVENT_ROLE,
				"update_field": "status", "update_value": state}
			for state in ("Pending Approval", "Rejected", "Editing")
		],
		"transitions": [
			{"state": "Pending Approval", "action": BATCH_FAILURE_ACTION, "next_state": "Rejected",
				"allowed": WORKFLOW_EVENT_ROLE, "allow_self_approval": 1,
				"custom_parallel_approval_policy": "Any"},
			{"state": "Rejected", "action": BATCH_FAILURE_FOLLOW_UP, "next_state": "Editing",
				"allowed": WORKFLOW_EVENT_ROLE, "allow_self_approval": 1,
				"condition": "doc.custom_data != 'blocked'", "custom_parallel_approval_policy": "Any"},
		],
	}).insert(ignore_permissions=True)
	blocked = fixture["positions"][1] if block_one else None
	frappe.db.set_value("User Timesheet", fixture["name"], "ut_status", "Pending Approval")
	for name in fixture["positions"]:
		frappe.db.set_value(position_doctype, name, {
			"status": "Pending Approval",
			"custom_data": "blocked" if name == blocked else "ready",
		})
		position = frappe.get_doc(position_doctype, name)
		# Prepare and pin the test's own Workflow without altering existing definitions.
		with patch.object(service, "select_workflow", return_value=workflow):
			context = service.ensure_context(position, persist_state=True)
		service.pin_process(position, context["process_id"])
		engine.reconcile_source(position)
	return {**fixture, "labels": labels, "blocked": blocked, "action": BATCH_FAILURE_ACTION,
		"workflow": workflow.name, "follow_up": BATCH_FAILURE_FOLLOW_UP}
