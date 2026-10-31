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
	lifecycle._should_handle = lambda _doc: False
	try:
		yield
	finally:
		lifecycle._should_handle = original


def _delete_workflow_tasks(position_name):
	tasks = frappe.get_all(
		"Workflow Task",
		filters={
			"reference_doctype": "User Timesheet Position",
			"reference_name": position_name,
		},
		pluck="name",
	)
	for task_name in tasks:
		frappe.delete_doc(
			"Workflow Task",
			task_name,
			ignore_permissions=True,
			force=True,
		)


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
