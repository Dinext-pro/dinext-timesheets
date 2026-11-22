"""Disposable Worker, calendar and project for the Application For Leave browser tests."""

import re

import frappe
from frappe.tests.ui_test_helpers import whitelist_for_tests
from frappe.utils import add_days, today

from dinext_common.tests.ui_test_helpers import PASSWORD, _delete_tasks_for, _ensure_role, _ensure_user

LEAVE = "Application For Leave"


def _worker_email(marker: str) -> str:
	if frappe.session.user != "Administrator" or not frappe.local.dev_server:
		raise frappe.PermissionError("A development Administrator must manage this fixture")
	if not re.fullmatch(r"afl-cypress-[a-z0-9]{12}", marker):
		raise frappe.ValidationError("Invalid leave fixture name")
	return f"{marker}@example.invalid"


@whitelist_for_tests(methods=["POST"])
def cleanup(marker: str) -> None:
	email = _worker_email(marker)
	leaves = frappe.get_all(LEAVE, filters={"lauser": email}, pluck="name")
	_delete_tasks_for(LEAVE, leaves)
	if leaves:
		for doctype in ("Workflow Document Context", "Workflow Process"):
			frappe.db.delete(doctype, {"reference_doctype": LEAVE, "reference_name": ("in", leaves)})
	for name in leaves:
		frappe.delete_doc(LEAVE, name, force=True, ignore_permissions=True)
	if frappe.db.exists("Project", marker):
		frappe.db.delete("Project Team Details", {"parent": marker, "parenttype": "Project"})
		frappe.delete_doc("Project", marker, force=True, ignore_permissions=True)
	for doctype in ("Worker", "User Group", "Timesheet Template", "Working Hours On Date",
		"Holiday List", "Type Of Leave", "Project Role"):
		frappe.delete_doc_if_exists(doctype, marker, force=True)
	frappe.delete_doc_if_exists("User", email, force=True)
	for table in ("DocPerm", "Custom DocPerm"):
		frappe.db.delete(table, {"parent": "Kanban Board", "role": marker})
	frappe.delete_doc_if_exists("Role", marker, force=True)
	frappe.clear_cache(doctype="Kanban Board")


@whitelist_for_tests(methods=["POST"])
def seed(marker: str) -> dict:
	email = _worker_email(marker)
	if "dinext_projects" not in frappe.get_installed_apps():
		raise frappe.ValidationError("The leave allocation browser test requires dinext_projects")

	start = add_days(today(), 7)
	holiday = add_days(start, 1)
	end = add_days(start, 2)
	overlap_end = add_days(start, 3)

	def create(doctype: str, **values):
		return frappe.get_doc({"doctype": doctype, **values}).insert(ignore_permissions=True, set_name=marker)

	previous_mute = frappe.flags.get("mute_emails")
	frappe.flags.mute_emails = True
	try:
		_ensure_role(marker)
		layer = "Custom DocPerm" if frappe.db.exists("Custom DocPerm", {"parent": "Kanban Board"}) else "DocPerm"
		frappe.get_doc({
			"doctype": layer, "parent": "Kanban Board", "parenttype": "DocType", "parentfield": "permissions",
			"role": marker, "read": 1, "permlevel": 0, "if_owner": 1,
		}).db_insert()
		frappe.clear_cache(doctype="Kanban Board")
		_ensure_user(email, marker, ["System Manager", "Dinext_Worker", "Dinext_UT_Full_Access", marker])
		create("Holiday List", holiday_list_name=marker, from_date=start, to_date=overlap_end,
			holidays=[{"holiday_date": holiday, "description": "Synthetic holiday"}])
		create("Working Hours On Date", hod_subject=marker, hod_from_date=start, hod_to_date=overlap_end)
		create("Timesheet Template", ttsubject=marker, enabled=1, ttreporting_period="Недельный",
			tt_working_hours_on_date=marker, hours_on_date=8,
			minimum_hours=0, maximum_hours=8, working_days=1,
			doctype_for_timesheet=[{"dtdoctype": "Task"}])
		create("User Group", user_group_members=[{"user": email}])
		create("Worker", wuser=email, wuser_group=marker, wholiday_list=marker,
			wtimesheet_template=marker, wvalid_from=start)
		create("Type Of Leave")
		frappe.get_doc({"doctype": "Project Role", "name": marker}).db_insert()
		frappe.get_doc({
			"doctype": "Project", "name": marker, "project_name": marker,
			"company": frappe.db.get_value("Company", {}, "name"), "status": "Open",
		}).db_insert()
		frappe.get_doc({
			"doctype": "Project Team Details", "name": marker, "parent": marker,
			"parenttype": "Project", "parentfield": "custom_project_team", "pt_role": marker,
			"pt_participant_type": "User", "pt_participant": email,
			"pt_valid_from": start, "pt_valid_for": end,
		}).db_insert()

		leave = frappe.get_doc({
			"doctype": LEAVE, "lauser": email, "alworker": marker, "altype_of_leave": marker,
			"status": "Editing", "alfrom_date": start, "alto_date": end,
			"alfrom_hours": "3", "alto_hours": "4", "alreasons": marker,
		}).insert(ignore_permissions=True)
		# Start the browser scenario at the valid pending form. Save through the
		# application so its validators compute hours and build project rows.
		frappe.db.set_value(LEAVE, leave.name, "status", "Pending Approval")
		leave.reload().save(ignore_permissions=True)
		return {
			"worker": marker, "user": email, "password": PASSWORD, "leave": leave.name,
			"start": start, "end": end, "overlap_end": overlap_end,
		}
	finally:
		frappe.flags.mute_emails = previous_mute
