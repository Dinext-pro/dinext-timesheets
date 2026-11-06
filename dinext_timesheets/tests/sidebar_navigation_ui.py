"""Owned, development-only records for timesheet navigation acceptance."""

from contextlib import ExitStack
from unittest.mock import patch

import frappe
from frappe.tests.ui_test_helpers import whitelist_for_tests
from frappe.utils import add_days, date_diff, getdate
from frappe.utils.password import update_password

PREFIX = "_Cypress TS Sidebar"
USER = "cy.ts.sidebar@example.com"
ROLE = PREFIX + " Reader"
PASSWORD = "Cypress-TS-Sidebar-2026!"
TIMESHEET = PREFIX + " Timesheet"
GROUP = PREFIX + " Group"
WORKER = PREFIX + " Worker"


@whitelist_for_tests
def cleanup_sidebar_navigation():
	from frappe.model.utils.user_settings import sync_user_settings

	sync_user_settings()
	if frappe.db.exists("User Timesheet", TIMESHEET):
		frappe.delete_doc("User Timesheet", TIMESHEET, force=True, ignore_permissions=True)
	for name in frappe.get_all("Worker", filters={"wuser": USER}, pluck="name"):
		frappe.delete_doc("Worker", name, force=True, ignore_permissions=True)
	for doctype, name in (("User Group", GROUP), ("User", USER)):
		if frappe.db.exists(doctype, name):
			frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
	frappe.db.delete("Custom DocPerm", {"role": ROLE})
	frappe.db.delete("DocType Permission Condition", {"role": ROLE})
	if frappe.db.exists("Role", ROLE):
		frappe.delete_doc("Role", ROLE, force=True, ignore_permissions=True)
	settings = frappe.qb.Table("__UserSettings")
	frappe.qb.from_(settings).delete().where(settings.user == USER).run()
	frappe.cache.delete_value("doctype_permission_map")
	frappe.clear_cache()
	frappe.db.after_commit.add(frappe.clear_cache)
	return {"cleaned": True}


def _calendar():
	for worker in frappe.get_all(
		"Worker",
		filters={"wholiday_list": ["!=", ""], "wtimesheet_template": ["!=", ""]},
		fields=["wholiday_list", "wtimesheet_template"],
		limit=50,
	):
		holiday = frappe.db.get_value(
			"Holiday List", worker.wholiday_list, ["from_date", "to_date"], as_dict=True
		)
		if not holiday or not holiday.from_date or not holiday.to_date:
			continue
		start, end = getdate(holiday.from_date), getdate(holiday.to_date)
		hours_name = frappe.db.get_value(
			"Timesheet Template", worker.wtimesheet_template, "tt_working_hours_on_date"
		)
		if hours_name:
			hours = frappe.db.get_value(
				"Working Hours On Date", hours_name, ["hod_from_date", "hod_to_date"], as_dict=True
			)
			if not hours or not hours.hod_from_date or not hours.hod_to_date:
				continue
			start, end = max(start, getdate(hours.hod_from_date)), min(end, getdate(hours.hod_to_date))
		if date_diff(end, start) >= 6:
			return worker, start, add_days(start, 6)
	frappe.throw("The sidebar fixture needs an existing seven-day worker calendar")


def _permissions():
	doctypes = (
		"User Timesheet",
		"User Timesheet Position",
		"Project",
		"Project Role",
		"Issue",
		"Task",
		"Kanban Board",
		"Report",
		"Support Settings",
		"Timesheet Template",
		"Holiday List",
		"Working Hours On Date",
		"Worker",
	)
	for doctype in doctypes:
		frappe.get_doc(
			{
				"doctype": "Custom DocPerm",
				"parent": doctype,
				"parenttype": "DocType",
				"parentfield": "permissions",
				"role": ROLE,
				"permlevel": 0,
				"read": 1,
				"select": 1,
			}
		).insert(ignore_permissions=True)
	for parent in frappe.get_all(
		"DocType Permission", filters={"ref_doctype": ["in", list(doctypes)]}, pluck="name"
	):
		frappe.get_doc(
			{
				"doctype": "DocType Permission Condition",
				"parent": parent,
				"parenttype": "DocType Permission",
				"parentfield": "conditions",
				"idx": frappe.db.count("DocType Permission Condition", {"parent": parent}) + 1,
				"role": ROLE,
				"perm_level": "Full Access",
				"script": 'conditions = "true"',
			}
		).db_insert()
	frappe.cache.delete_value("doctype_permission_map")


@whitelist_for_tests
def seed_sidebar_navigation():
	cleanup_sidebar_navigation()
	calendar, start, end = _calendar()
	frappe.get_doc({"doctype": "Role", "role_name": ROLE}).insert(ignore_permissions=True)
	user = frappe.get_doc(
		{
			"doctype": "User",
			"email": USER,
			"first_name": "Cypress Sidebar Owner",
			"enabled": 1,
			"user_type": "System User",
			"send_welcome_email": 0,
			"language": "en",
			"desk_theme": "Light",
			"onboarding_status": frappe.as_json(
				{name: {"is_complete": True} for name in frappe.get_all("Form Tour", pluck="name")}
			),
		}
	)
	for role in (ROLE, "Desk User", "System Manager", "Dinext_Worker", "Dinext_UT_Full_Access"):
		if frappe.db.exists("Role", role):
			user.append("roles", {"role": role})
	with ExitStack() as stack:
		if "raven" in frappe.get_installed_apps():
			stack.enter_context(
				patch("raven.raven.doctype.raven_user.raven_user.add_user_to_raven", return_value=None)
			)
		user.insert(ignore_permissions=True)
	update_password(USER, PASSWORD)
	_permissions()
	frappe.get_doc(
		{
			"doctype": "User Group",
			"name": GROUP,
			"user_group_members": [{"user": USER}],
		}
	).insert(ignore_permissions=True)
	frappe.get_doc(
		{
			"doctype": "Worker",
			"name": WORKER,
			"wuser": USER,
			"wfullname": "Cypress Sidebar Owner",
			"wuser_group": GROUP,
			"wvalid_from": start,
			"wtimesheet_template": calendar.wtimesheet_template,
			"wholiday_list": calendar.wholiday_list,
		}
	).db_insert()
	status_field = frappe.get_meta("User Timesheet").get_field("ut_status")
	options = (status_field.options or "").splitlines()
	status = next((s for s in ("Draft", "Черновик") if s in options), status_field.default)
	frappe.get_doc(
		{
			"doctype": "User Timesheet",
			"name": TIMESHEET,
			"owner": USER,
			"timesheet_from": USER,
			"timesheet_from_name": "Cypress Sidebar Owner",
			"user_group": GROUP,
			"ts_valid_from": start,
			"ts_valid_for": end,
			"ut_status": status,
			"total_hours_schedule": 40,
			"total_hours_to_work": 40,
		}
	).db_insert()
	frappe.clear_cache()
	frappe.db.after_commit.add(frappe.clear_cache)
	return {"user": USER, "password": PASSWORD, "timesheet": TIMESHEET}
