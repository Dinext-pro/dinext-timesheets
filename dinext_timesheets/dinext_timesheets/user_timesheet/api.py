"""Whitelist facades for User Timesheet (ISS-2026-00926 try3).

Port from demodev Server Scripts — see try3/timesheet/inventory-demodev.md.
Limits: call project_workload_assignment.api.calculate_user_timesheet_limits
(ISS-2026-02105 unified calculator; later move here). Do not duplicate.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import add_days, get_last_day, getdate

from dinext_timesheets.timesheet_status import PARENT_DRAFT
from .copy_positions import (
	copy_from_previous_timesheet,
	copy_from_project_workload_assignment,
)
from .pending_approvers import list_pending_approver_names
from .permissions import (
	assert_can_create_for_worker,
	assert_can_edit_timesheet,
	assert_can_query_tasks_for_owner,
	can_edit_timesheet,
)
from .status import set_timesheet_status as _set_timesheet_status
from .tasks import load_projects_remap2_customers


def _form_arg(name: str, explicit=None):
	if explicit is not None and explicit != "":
		return explicit
	return frappe.form_dict.get(name)


def _worker_calendar(user):
	worker = frappe.db.get_value(
		"Worker", {"wuser": user}, ["wtimesheet_template", "wholiday_list", "wuser_group"], as_dict=True
	)
	if not worker or not worker.wtimesheet_template:
		frappe.throw(_("The employee has no timesheet template"))
	template = frappe.db.get_value(
		"Timesheet Template",
		worker.wtimesheet_template,
		[
			"name", "ttreporting_period", "tt_working_hours_on_date",
			"hours_on_date", "minimum_hours", "maximum_hours", "_is_mandatory",
		],
		as_dict=True,
	)
	if not template:
		frappe.throw(_("The employee has no timesheet template"))
	return worker, template


def _period_end(start, reporting_period):
	month_end = get_last_day(start)
	if reporting_period == "Месячный":
		return month_end
	if reporting_period == "Полумесячный":
		return add_days(start, 15)
	if reporting_period in {"Недельный", "Недельный по конец месяца"}:
		return min(month_end, add_days(start, 6 - start.weekday()))
	frappe.throw(_("Could not determine the timesheet period from the template"))


def _new_timesheet_context(worker, start):
	if not worker or not start:
		frappe.throw(_("Please fill in all required fields"))
	calendar, template = _worker_calendar(worker)
	end = _period_end(getdate(start), template.ttreporting_period)
	assert_can_create_for_worker(worker, end)
	return calendar, template, end


def validate_timesheet_write(doc):
	if doc.flags.ignore_permissions or doc.is_new():
		return
	before = doc.get_doc_before_save()
	if any(
		doc.get(field) != before.get(field)
		for field in ("timesheet_from", "ut_status", "user_group")
	) or any(
		(doc.get(field) and getdate(doc.get(field))) != (before.get(field) and getdate(before.get(field)))
		for field in ("ts_valid_from", "ts_valid_for")
	):
		frappe.throw(_("Timesheet ownership, period and status are managed by the system"), frappe.PermissionError)
	assert_can_edit_timesheet(before)


def prepare_timesheet_insert(doc):
	if doc.flags.ignore_permissions:
		return
	# Serialize overlap checks for concurrent creation of the same worker's timesheet.
	frappe.db.get_value("Worker", {"wuser": doc.timesheet_from}, "name", for_update=True)
	calendar, template, end = _new_timesheet_context(doc.timesheet_from, doc.ts_valid_from)
	if doc.ts_valid_for and getdate(doc.ts_valid_for) != end:
		frappe.throw(_("The timesheet end date does not match its reporting period"))
	if doc.ut_status and doc.ut_status != PARENT_DRAFT:
		frappe.throw(_("A new timesheet must be a draft"), frappe.PermissionError)
	doc.update({
		"ts_valid_for": end,
		"timesheet_from_name": frappe.db.get_value("User", doc.timesheet_from, "full_name"),
		"ts_from_template": template.name,
		"reporting_period": template.ttreporting_period,
		"user_group": calendar.wuser_group,
	})
	if frappe.db.exists(
		"User Timesheet",
		{"timesheet_from": doc.timesheet_from, "ts_valid_from": ("<=", end),
		 "ts_valid_for": (">=", doc.ts_valid_from)},
	):
		frappe.throw(_("A timesheet already exists that overlaps these dates"))


@frappe.whitelist()
def get_timesheet_context(timesheet=None, worker=None, start=None):
	"""Return only the form data needed for an authorized worker and period."""
	if not timesheet:
		_calendar, template, end = _new_timesheet_context(worker, start)
		return {"template": template, "end": end}

	parent = frappe.get_doc("User Timesheet", timesheet)
	parent.check_permission("read")
	calendar, template = _worker_calendar(parent.timesheet_from)
	dates = ("between", (parent.ts_valid_from, parent.ts_valid_for))
	return {
		"template": template,
		"can_edit": can_edit_timesheet(parent),
		"holidays": frappe.get_all(
			"Holiday", filters={"parent": calendar.wholiday_list, "holiday_date": dates},
			fields=["holiday_date", "description"],
		) if calendar.wholiday_list else [],
		"work_hours": frappe.get_all(
			"Working Hours Table", filters={"parent": template.tt_working_hours_on_date, "wht_date": dates},
			fields=["wht_date", "wht_hours"],
		) if template.tt_working_hours_on_date else [],
	}


@frappe.whitelist()
def get_timesheet_tasks(template_name=None, ts_start=None, ts_end=None, ts_owner=None):
	"""Return customer→projects→tasks/issues tree for UT task picker."""
	owner = _form_arg("ts_owner", ts_owner)
	start = _form_arg("ts_start", ts_start)
	end = _form_arg("ts_end", ts_end)
	assert_can_query_tasks_for_owner(owner, start, end)
	_calendar, template = _worker_calendar(owner)
	return load_projects_remap2_customers(
		template.name,
		start,
		end,
		owner,
	)


@frappe.whitelist()
def copy_positions_from_previous_timesheet(doc=None):
	"""Candidates to copy from previous period UT."""
	return copy_from_previous_timesheet(_form_arg("doc", doc))


@frappe.whitelist()
def copy_positions_from_project_workload_assignment(doc=None, valid_tasks=None):
	"""Candidates to copy from Project Workload Assignment."""
	return copy_from_project_workload_assignment(
		_form_arg("doc", doc),
		_form_arg("valid_tasks", valid_tasks),
	)


@frappe.whitelist()
def set_timesheet_status(positions=None, pos_status=None, ts_name=None, ts_status=None):
	"""Legacy status adapter for sites that use the Frappe workflow engine."""
	from dinext_common.workflow_approval.lifecycle import is_engine_enabled

	if is_engine_enabled():
		frappe.throw(_("Use the position Workflow to change the timesheet status"), frappe.PermissionError)
	return _set_timesheet_status(
		positions=_form_arg("positions", positions),
		pos_status=_form_arg("pos_status", pos_status),
		ts_name=_form_arg("ts_name", ts_name),
		ts_status=_form_arg("ts_status", ts_status),
	)


@frappe.whitelist()
def get_pending_approver_names(ts_name=None):
	"""Banner: all waiting approver full names (not only session user)."""
	return list_pending_approver_names(_form_arg("ts_name", ts_name))
