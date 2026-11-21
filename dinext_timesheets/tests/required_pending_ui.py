"""Temporary records for Timesheet pending approver and audit comment displays."""

import frappe
from frappe.tests.ui_test_helpers import whitelist_for_tests

from dinext_common.tests.required_pending_ui import _set_workflow_comments, _tasks, _workflow
from dinext_common.tests.ui_test_helpers import (
	PASSWORD,
	_assert_flag,
	_delete_tasks_for,
	_ensure_permission_condition,
	_ensure_read_perm,
	_ensure_role,
	_ensure_user,
)

FIXTURE_KEY = "cypress_timesheet_required_pending"
NAME = "Cypress Timesheet Required Pending"
ROLE = NAME + " Reader"
TITLES = ("Cypress Pending Viewer", "Cypress Required Actor", "Cypress Optional Actor", "Cypress Mixed Actor")
USERS = tuple(f"cypress.ts.pending.{label}@example.invalid" for label in ("viewer", "required", "optional", "mixed"))
POSITION = "User Timesheet Position"


def _require_admin():
	if frappe.session.user != "Administrator" or not frappe.local.dev_server:
		raise frappe.PermissionError("A development Administrator must manage this fixture")


@whitelist_for_tests(methods=["POST"])
def cleanup_required_pending_cypress():
	_require_admin()
	positions = frappe.get_all(POSITION, filters={"user_timesheet": NAME}, pluck="name")
	previous = frappe.flags.in_workflow_task_retention
	try:
		_delete_tasks_for(POSITION, positions)
		_delete_tasks_for("User Timesheet", [NAME])
	finally:
		frappe.flags.in_workflow_task_retention = previous
	for name in positions:
		# These test positions are inserted directly in Pending Approval.
		frappe.delete_doc(POSITION, name, force=True, ignore_permissions=True, ignore_on_trash=True)
	for doctype in (
		"User Timesheet", "Workflow", "Worker", "User Group", "Timesheet Template",
		"Working Hours On Date", "Holiday List",
	):
		frappe.delete_doc_if_exists(doctype, NAME, force=True)
	for user in USERS:
		frappe.delete_doc_if_exists("User", user, force=True)
	for doctype in ("Custom DocPerm", "DocType Permission Condition"):
		frappe.db.delete(doctype, {"role": ROLE})
	frappe.delete_doc_if_exists("Role", ROLE, force=True)
	frappe.cache.delete_value(FIXTURE_KEY)
	frappe.clear_cache()


@whitelist_for_tests(methods=["POST"])
def seed_required_pending_cypress():
	_require_admin()
	_assert_flag()
	cleanup_required_pending_cypress()
	_ensure_role(ROLE)
	for doctype in ("User Timesheet", POSITION, "Kanban Board", "Report", "Worker", "Timesheet Template",
		"Holiday List", "Working Hours On Date", "Timesheet Settings", "User Group"):
		_ensure_read_perm(doctype, ROLE)
	for parent in ("UT_Permissions-1", "UTP_Permissions-1"):
		_ensure_permission_condition(parent, ROLE)
	for user, title in zip(USERS, TITLES, strict=True):
		_ensure_user(user, title, [ROLE, "Desk User", "System Manager", "Dinext_Worker"])

	start, end = "2039-01-03", "2039-01-09"
	viewer = USERS[0]
	for doctype, values in (
		("Holiday List", {"holiday_list_name": NAME, "from_date": start, "to_date": end}),
		("Working Hours On Date", {"hod_subject": NAME, "hod_from_date": start, "hod_to_date": end}),
		("Timesheet Template", {"ttsubject": NAME, "tt_working_hours_on_date": NAME, "hours_on_date": 8,
			"enabled": 1, "ttreporting_period": "Недельный"}),
		("User Group", {}),
		("Worker", {"wuser": viewer, "wfullname": TITLES[0], "wuser_group": NAME,
			"wtimesheet_template": NAME, "wholiday_list": NAME, "wvalid_from": start}),
		("User Timesheet", {"timesheet_from": viewer, "timesheet_from_name": TITLES[0],
			"ts_valid_from": start, "ts_valid_for": end, "ut_status": "Pending Approval"}),
	):
		frappe.get_doc({"doctype": doctype, "name": NAME, **values}).db_insert()
	workflow = _workflow(NAME, POSITION, "status", "Pending Approval", "Approved", "Editing", role=ROLE)
	positions = []
	for index in range(2):
		position = frappe.get_doc({
			"doctype": POSITION, "name": f"{NAME} {index}", "user_timesheet": NAME,
			"user": viewer, "status": "Pending Approval",
		})
		position.db_insert()
		_tasks(position, workflow, "Pending Approval", "Approved", "Editing",
			users=USERS, role=ROLE, second=bool(index))
		positions.append(position.name)

	frappe.clear_cache()
	frappe.cache.set_value(FIXTURE_KEY, positions)
	return {
		"timesheet": NAME, "positions": positions, "viewer": viewer, "password": PASSWORD,
		"viewer_name": TITLES[0], "required": TITLES[1], "optional": TITLES[2], "mixed": TITLES[3],
	}


@whitelist_for_tests(methods=["POST"])
def set_required_pending_optional(optional: int):
	_fixture_positions()
	if int(optional) not in (0, 1):
		raise frappe.ValidationError("Unknown fixture metadata")
	frappe.db.set_value("Workflow Document State", {"parent": NAME, "state": "Approved"},
		"is_optional_state", int(optional))
	return {"optional": int(optional)}


@whitelist_for_tests(methods=["POST"])
def set_workflow_comments_cypress(mode: str):
	return _set_workflow_comments(POSITION, _fixture_positions(), NAME, "Pending Approval", USERS, mode)


def _fixture_positions():
	_assert_flag()
	positions = frappe.cache.get_value(FIXTURE_KEY)
	if not positions or frappe.session.user not in (USERS[0], "Administrator"):
		raise frappe.PermissionError("Only the fixture viewer may edit its display metadata")
	return positions
