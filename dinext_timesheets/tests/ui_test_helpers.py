"""Dev-server fixture for the User Timesheet form Cypress spec.

Creates and deletes its own timesheet. Requires a Worker with a holiday list
already on the site. Methods refuse to run unless the process is a
development server (`DEV_SERVER=1`).
"""

from __future__ import annotations

import frappe
from frappe.tests.ui_test_helpers import whitelist_for_tests
from frappe.utils import add_days, date_diff, getdate

MARKER = "cypress-ut-form"


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
			"ut_status": "Черновик",
		}
	)
	doc.insert(ignore_permissions=True)
	return {"name": doc.name}
