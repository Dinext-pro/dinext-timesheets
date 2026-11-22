"""Disposable approval comments and pending tasks for the leave form."""

import frappe
from frappe.tests.ui_test_helpers import whitelist_for_tests


LEAVE = "Cypress Workflow Audit Leave"
LEAVE_USER = "cy.workflow.audit.leave@example.com"
LEAVE_USER_RU = "cy.workflow.audit.leave.ru@example.com"
LEAVE_APPROVER = "cy.workflow.audit.leave.approver@example.com"
LEAVE_REVIEWER = "cy.workflow.audit.leave.reviewer@example.com"
LEAVE_PENDING = "cy.workflow.audit.leave.pending@example.com"
LEAVE_ROLE = "Cypress Workflow Audit Leave Viewer"
LEAVE_DEPENDENCIES = ("Worker", "User Group", "Timesheet Template", "Holiday List")


def _require_workflow_test_site():
	if not (
		frappe.session.user == "Administrator"
		and getattr(frappe.local, "dev_server", False)
		and frappe.conf.get("workflow_scenarios_test_site")
	):
		raise frappe.PermissionError("Workflow acceptance requires an isolated development test site")


@whitelist_for_tests(methods=["POST"])
def cleanup_workflow_comment_leave():
	"""Delete the isolated AFL form, approval rows and assigned test users."""
	from dinext_common.tests.ui_test_helpers import _delete_tasks_for

	_require_workflow_test_site()
	doctype = "Application For Leave"
	previous = frappe.flags.in_workflow_task_retention
	try:
		_delete_tasks_for(doctype, [LEAVE])
	finally:
		frappe.flags.in_workflow_task_retention = previous
	frappe.delete_doc(doctype, LEAVE, force=True, ignore_permissions=True)
	for table in ("Workflow Document Context", "Workflow Process"):
		frappe.db.delete(table, {"reference_doctype": doctype, "reference_name": LEAVE})
	for table in LEAVE_DEPENDENCIES:
		frappe.delete_doc(table, LEAVE, force=True, ignore_permissions=True)
	for user in (LEAVE_USER, LEAVE_USER_RU, LEAVE_APPROVER, LEAVE_REVIEWER, LEAVE_PENDING):
		frappe.delete_doc("User", user, force=True, ignore_permissions=True)
	for table in ("Custom DocPerm", "DocType Permission Condition"):
		frappe.db.delete(table, {"role": LEAVE_ROLE})
	frappe.delete_doc("Role", LEAVE_ROLE, force=True, ignore_permissions=True)
	frappe.clear_cache()


@whitelist_for_tests(methods=["POST"])
def seed_workflow_comment_leave():
	"""Prepare an AFL with one pending reviewer and two completed required comments."""
	import json

	from dinext_common.tests.ui_test_helpers import (
		PASSWORD as APPROVAL_PASSWORD,
		_ensure_permission_condition,
		_ensure_read_perm,
		_ensure_role,
		_ensure_user,
		_manual_task,
	)
	from dinext_common.workflow_approval.scenarios import service

	cleanup_workflow_comment_leave()
	_ensure_role(LEAVE_ROLE)
	doctype, state = "Application For Leave", "Pending Approval"
	for table in (doctype, *LEAVE_DEPENDENCIES, "Type Of Leave", "Report", "Kanban Board"):
		_ensure_read_perm(table, LEAVE_ROLE)
	_ensure_permission_condition("AFL_Permissions-1", LEAVE_ROLE)
	authored = (
		(LEAVE_APPROVER, "Cypress Leave Approver", "Correct these dates"),
		(LEAVE_REVIEWER, "Cypress Leave Reviewer", "Attach the details"),
	)
	_ensure_user(LEAVE_USER, "Cypress Leave Viewer", [LEAVE_ROLE, "Desk User", "Dinext_Worker"])
	_ensure_user(LEAVE_USER_RU, "Cypress Leave Viewer RU", [LEAVE_ROLE, "Desk User", "Dinext_Worker"])
	frappe.db.set_value("User", LEAVE_USER_RU, "language", "ru", update_modified=False)
	frappe.clear_cache(user=LEAVE_USER_RU)
	for user, full_name, _ in authored:
		_ensure_user(user, full_name, [LEAVE_ROLE, "Desk User"])

	for table, values in (
		("Holiday List", {"holiday_list_name": LEAVE, "from_date": "2039-01-01", "to_date": "2039-12-31"}),
		("Timesheet Template", {"ttsubject": LEAVE}),
		("User Group", {}),
		("Worker", {"wuser": LEAVE_USER, "wfullname": LEAVE, "wuser_group": LEAVE,
			"wtimesheet_template": LEAVE, "wholiday_list": LEAVE, "wvalid_from": "2039-01-01"}),
	):
		frappe.get_doc({"doctype": table, "name": LEAVE, **values}).db_insert()

	workflow = frappe.get_doc("Workflow", {"document_type": doctype, "is_active": 1})
	source = frappe.get_doc({
		"doctype": doctype, "name": LEAVE, "lauser": LEAVE_USER, "lauser_name": LEAVE,
		"alworker": LEAVE, "altype_of_leave": frappe.db.get_value("Type Of Leave", {}, "name"),
		"alfrom_date": "2039-01-11", "alto_date": "2039-01-12", "status": state,
		workflow.workflow_state_field: state,
	})
	source.db_insert()
	source.reload()
	round_id = frappe.generate_hash(length=40)
	def make_task(user, status, comment=None):
		name = _manual_task(
			doctype=doctype, name=source.name, workflow=workflow.name, state=state, approver=user,
			round_status="Open", status=status, round_id=round_id, allowed_role=LEAVE_ROLE,
			action="Reject" if comment else "Approve", next_state="Rejected" if comment else "Approved",
			transition_uuid="leave-reject" if comment else "leave-approve",
		)
		frappe.db.set_value("Workflow Task", name, {
			"source_created_at": source.creation,
			"vote_comment": comment,
			"transition_uuid": "leave-reject" if comment else None,
			"round_manifest": json.dumps({"transitions": [
				{"transition_uuid": "leave-reject", "comment_is_required": True},
			]}),
		}, update_modified=False)
		return frappe.get_doc("Workflow Task", name).as_dict()

	_ensure_user(LEAVE_PENDING, "Cypress Leave Pending Approver", [LEAVE_ROLE, "Desk User"])
	rows = [make_task(user, "Completed", comment) for user, _, comment in authored]
	rows.append(make_task(LEAVE_PENDING, "Working"))
	service.adopt_legacy_source(source, rows)
	return {
		"viewers": {"en": LEAVE_USER, "ru": LEAVE_USER_RU}, "password": APPROVAL_PASSWORD, "leave": LEAVE,
		"pending": "Cypress Leave Pending Approver",
		"authors": [name for _, name, _ in authored], "comments": [comment for _, _, comment in authored],
	}
