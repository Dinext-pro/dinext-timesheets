"""Owned plan/fact records shared by the timesheet and common-dialog browser projects."""

from __future__ import annotations

import frappe
from dinext_common.tests.ui_test_helpers import _ensure_permission_condition, _ensure_read_perm
from frappe.tests.ui_test_helpers import whitelist_for_tests
from frappe.utils import getdate

from dinext_timesheets.tests import utp_list_ui as base

PREFIX = "_Cypress Limits Dialog"
PARENT = PREFIX + " Parent"
TASK = PREFIX + " Task"
ROLE_B = PREFIX + " Analyst"


def _sync_preferences():
	from frappe.model.utils.user_settings import sync_user_settings

	sync_user_settings()


@whitelist_for_tests
def cleanup_limits_dialog():
	_sync_preferences()
	for name in frappe.get_all("Project Work Efforts", filters={"pwe_project": base.PROJECT}, pluck="name"):
		frappe.delete_doc("Project Work Efforts", name, force=True, ignore_permissions=True)
	# These display-only tasks are inserted without lifecycle or nested-set side effects.
	# They own no dependencies/notifications; deleting them leaves real task indices intact.
	for name in (TASK, PARENT):
		frappe.db.delete("Task", {"name": name, "project": base.PROJECT})
	base.cleanup_utp_list()
	if frappe.db.exists("Project Role", ROLE_B):
		frappe.delete_doc("Project Role", ROLE_B, force=True, ignore_permissions=True)
	return {"cleaned": True}


def _child_field(doctype, child):
	return next(field.fieldname for field in frappe.get_meta(doctype).fields if field.options == child)


def _plan(project, role, fiscal_year, month, plan, forecast):
	doc = frappe.get_doc(
		{
			"doctype": "Project Work Efforts",
			"name": PREFIX + " Plan " + role,
			"pwe_project": project,
			"pwe_task": PARENT,
			"pwe_project_role": role,
		}
	)
	doc.db_insert()
	doc.append(
		"pwe_amount",
		{
			"pwea_year": fiscal_year,
			"pwea_month": month,
			"pwea_plan": plan,
			"pwea_expected": forecast,
		},
	).db_insert()


@whitelist_for_tests
def seed_limits_dialog():
	cleanup_limits_dialog()
	fixture = base.seed_utp_list()
	for doctype in ("Task", "Project Work Efforts", "Project Work Efforts Amount", "Task Type"):
		_ensure_read_perm(doctype, base.ROLE)
	for parent in frappe.get_all("DocType Permission", filters={"ref_doctype": "Task"}, pluck="name"):
		_ensure_permission_condition(parent, base.ROLE)
	for doctype in ("User Timesheet", "User Timesheet Position"):
		for name in frappe.get_all(
			"Custom DocPerm", filters={"parent": doctype, "role": base.ROLE}, pluck="name"
		):
			frappe.db.set_value("Custom DocPerm", name, "write", 1, update_modified=False)
	for user in base.USERS:
		frappe.db.set_value("User", user, "language", "en", update_modified=False)
	parent = frappe.get_doc("User Timesheet", fixture["timesheet"])
	start, end = getdate(parent.ts_valid_from), getdate(parent.ts_valid_for)
	fiscal_year = frappe.db.get_value(
		"Fiscal Year",
		{
			"year_start_date": ("<=", start),
			"year_end_date": (">=", start),
		},
		"name",
	)
	if not fiscal_year:
		frappe.throw("The limit-detail fixture needs an existing Fiscal Year for its dates")
	frappe.get_doc({"doctype": "Project Role", "name": ROLE_B}).db_insert()
	project = frappe.get_doc("Project", base.PROJECT)
	team_field = _child_field("Project", "Project Team Details")
	worker = frappe.db.get_value("Worker", {"wuser": base.OWNER}, "name")
	for role in (base.PROJECT_ROLE, ROLE_B):
		project.append(
			team_field, {"pt_role": role, "pt_worker": worker, "pt_participant": base.OWNER}
		).db_insert()
	limits_field = _child_field("Project", "Limit Control")
	for kind, value in (("Блокировка", 150), ("Предупреждение", 100)):
		project.append(limits_field, {"type": kind, "limit": value}).db_insert()
	frappe.db.set_value(
		"Project",
		project.name,
		"custom_обязательность_плановых_трудозатрат",
		"Опционально",
		update_modified=False,
	)
	for name, subject, group, parent_task in (
		(PARENT, "Cypress Limits Parent", 1, None),
		(TASK, "Cypress Shared Limits", 0, PARENT),
	):
		frappe.get_doc(
			{
				"doctype": "Task",
				"name": name,
				"subject": subject,
				"project": project.name,
				"is_group": group,
				"parent_task": parent_task,
				"status": "Open",
				"exp_start_date": start,
				"exp_end_date": end,
			}
		).db_insert()
	_plan(project.name, base.PROJECT_ROLE, fiscal_year, start.month, 280, 300)
	_plan(project.name, ROLE_B, fiscal_year, start.month, 140, 150)
	for index, (status, hours) in enumerate((("Pending Approval", 2), ("Approved", 280), ("Editing", 40))):
		name = fixture["positions"][index]["name"]
		frappe.db.set_value(
			"User Timesheet Position",
			name,
			{
				"document_type": "Task",
				"document_name": TASK,
				"status": status,
				"workflow_state": status,
				"all_hours": hours,
			},
			update_modified=False,
		)
		doc = frappe.get_doc("User Timesheet Position", name)
		doc.append(
			"table", {"date": start, "hours": hours, "description": "Cypress shared limit details"}
		).db_insert()
	fixture.update(
		{
			"task": TASK,
			"task_subject": "Cypress Shared Limits",
			"parent_task": PARENT,
			"parent_subject": "Cypress Limits Parent",
			"role": base.PROJECT_ROLE,
			"role_b": ROLE_B,
			"position": fixture["positions"][0]["name"],
			"editing_position": fixture["positions"][2]["name"],
			"date": str(start),
			"planned_hours": 280,
			"forecast_hours": 300,
			"total_hours": 322,
		}
	)
	frappe.clear_cache()
	return fixture


@whitelist_for_tests
def set_limits_case(required=False, empty_plan=False, language=None):
	"""Change only the owned project and plan amounts, or the owned user's language."""
	if not frappe.db.exists("Project", base.PROJECT):
		frappe.throw("Seed the owned limit-detail fixture first")
	frappe.db.set_value(
		"Project",
		base.PROJECT,
		"custom_обязательность_плановых_трудозатрат",
		"Обязательно для всех Задач" if frappe.utils.cint(required) else "Опционально",
		update_modified=False,
	)
	for plan in frappe.get_all(
		"Project Work Efforts", filters={"pwe_project": base.PROJECT}, fields=["name", "pwe_project_role"]
	):
		value = (
			0 if frappe.utils.cint(empty_plan) else 280 if plan.pwe_project_role == base.PROJECT_ROLE else 140
		)
		frappe.db.set_value(
			"Project Work Efforts Amount", {"parent": plan.name}, "pwea_plan", value, update_modified=False
		)
	if language:
		if language not in ("en", "ru"):
			frappe.throw("Unsupported fixture language")
		frappe.db.set_value("User", base.OWNER, "language", language, update_modified=False)
		frappe.clear_cache(user=base.OWNER)
	return {"updated": True}


def calculation_inputs(timesheet):
	"""Equivalent saved form/list/tree inputs for native server contract checks."""
	positions = []
	for name in frappe.get_all(
		"User Timesheet Position", filters={"user_timesheet": timesheet}, pluck="name"
	):
		doc = frappe.get_doc("User Timesheet Position", name)
		positions.append(
			{
				"name": name,
				"document_name": doc.document_name,
				"project": doc.project,
				"project_role": doc.project_role,
				"status": doc.status,
				"custom_username": doc.custom_username,
				"details": [{"date": str(row.date), "hours": row.hours} for row in doc.table],
			}
		)
	return positions
