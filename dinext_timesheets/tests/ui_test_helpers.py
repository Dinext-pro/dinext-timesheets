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
			"workflow_state": "Editing",
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
def seed_ut_workflow_stop(position_count: int = 1, editing_only: int = 0):
	"""Own user and position using the installed stop/edit workflow, without changing it."""
	from dinext_common.tests.ui_test_helpers import _ensure_read_perm
	from frappe.utils.password import update_password

	from dinext_timesheets.workflow_approval import get_timesheet_position_actions

	cleanup_ut_workflow_stop()
	frappe.get_doc({"doctype": "Role", "role_name": WORKFLOW_EVENT_ROLE}).insert(ignore_permissions=True)
	for doctype in ("Kanban Board", "Report", "Support Settings"):
		_ensure_read_perm(doctype, WORKFLOW_EVENT_ROLE)
	calendar = _worker()
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
	}).insert(ignore_permissions=True)
	positions = []
	with _pause_approval_engine():
		for _index in range(position_count):
			position = frappe.get_doc({
				"doctype": "User Timesheet Position", "user_timesheet": doc.name,
				"user": user.name, "status": "Editing", "workflow_state": "Editing",
			}).insert(ignore_permissions=True)
			positions.append(position.name)
	previous = frappe.session.user
	stop = None
	try:
		frappe.set_user(user.name)
		editing = get_timesheet_position_actions(doc.name)["actions"]
		if not editing:
			frappe.throw("Seeded timesheet owner has no action in Editing")
		if not editing_only:
			for name in positions:
				frappe.db.set_value("User Timesheet Position", name, {
					"status": "Pending Approval", "workflow_state": "Pending Approval",
				}, update_modified=False)
			frappe.db.set_value("User Timesheet", doc.name, "ut_status", "Pending Approval", update_modified=False)
			pending = get_timesheet_position_actions(doc.name)["actions"]
			stop = next(
				(row for row in pending if all(p["next_state"] == "Editing" for p in row["positions"])),
				None,
			)
			if not stop:
				frappe.throw("Seeded timesheet owner has no action to return to Editing")
	finally:
		frappe.set_user(previous)
	return {"name": doc.name, "position": positions[0], "positions": positions, "user": user.name,
		"password": password, "stop_action": stop["action"] if stop else None,
		"editing_actions": [row["action"] for row in editing]}
