"""Local Cypress fixture for exercising the empty timesheet card."""

import frappe
from frappe.tests.ui_test_helpers import whitelist_for_tests
from frappe.utils.password import update_password

PREFIX = "cypress-empty-ut-"


def _require_admin():
	if frappe.session.user != "Administrator" or not getattr(frappe.local, "dev_server", False):
		raise frappe.PermissionError


def _insert(doctype, fields, **kwargs):
	return frappe.get_doc({"doctype": doctype, **fields}).insert(ignore_permissions=True, **kwargs)


@whitelist_for_tests(methods=["POST"])
def seed():
	_require_admin()
	marker = PREFIX + frappe.generate_hash(length=10)
	user = _insert("User", {
		"email": marker + "@example.com", "first_name": marker, "send_welcome_email": 0,
		"roles": [{"role": "Dinext_Worker"}],
	}).name
	password = frappe.generate_hash(length=25) + "!7aZ"
	update_password(user, password)
	group = _insert("User Group", {"user_group_members": [{"user": user}]}, set_name=marker)
	calendar = _insert("Holiday List", {
		"holiday_list_name": marker, "from_date": "2026-11-01", "to_date": "2026-11-30",
		"holidays": [
			{"holiday_date": "2026-11-07", "description": "Weekend"},
			{"holiday_date": "2026-11-08", "description": "Weekend"},
		],
	})
	hours = _insert("Working Hours On Date", {
		"hod_subject": marker, "hod_from_date": "2026-11-01", "hod_to_date": "2026-11-30",
	})
	template = _insert("Timesheet Template", {
		"ttsubject": marker, "enabled": 1, "ttreporting_period": "Недельный",
		"hours_on_date": 8, "working_days": 0, "minimum_hours": 0, "maximum_hours": 0,
		"tt_working_hours_on_date": hours.name,
		"doctype_for_timesheet": [{"dtdoctype": "Task"}],
	})
	worker = _insert("Worker", {
		"wuser": user, "wuser_group": group.name, "wtimesheet_template": template.name,
		"wholiday_list": calendar.name, "wvalid_from": "2026-11-01",
	})
	sheet = _insert("User Timesheet", {
		"timesheet_from": user, "timesheet_from_name": marker, "ts_valid_from": "2026-11-07",
		"ts_valid_for": "2026-11-08", "ts_from_template": template.name, "ut_status": "Draft",
	}, set_name=marker)
	return {
		"name": sheet.name, "user": user, "password": password, "worker": worker.name,
		"calendar": calendar.name, "template": template.name, "group": group.name,
	}


@whitelist_for_tests(methods=["POST"])
def cleanup(name):
	_require_admin()
	if not name.startswith(PREFIX):
		raise frappe.ValidationError
	sheet = frappe.get_doc("User Timesheet", name)
	user = sheet.timesheet_from
	if user != name + "@example.com":
		raise frappe.ValidationError
	worker = frappe.get_doc("Worker", {"wuser": user})
	frappe.db.delete("Timesheet Submission Event", {"timesheet": name})
	frappe.delete_doc("User Timesheet", name, ignore_permissions=True, force=True)
	frappe.delete_doc("Worker", worker.name, ignore_permissions=True, force=True)
	hours = frappe.db.get_value("Timesheet Template", worker.wtimesheet_template, "tt_working_hours_on_date")
	for doctype, value in (
		("Timesheet Template", worker.wtimesheet_template),
		("Working Hours On Date", hours),
		("Holiday List", worker.wholiday_list),
		("User Group", worker.wuser_group),
		("User", user),
	):
		frappe.delete_doc(doctype, value, ignore_permissions=True, force=True)
	return True
