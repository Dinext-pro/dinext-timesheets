from __future__ import annotations

from datetime import date, timedelta

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, strip_html

AFL_PENDING_STATE = "Pending Approval"
AFL_APPROVED_STATE = "Approved"


def validate_application_for_leave(doc: Document) -> None:
	start_date, end_date = _leave_dates(doc)
	calculate_total_hours(doc, start_date, end_date)
	_run_project_handler("rebuild", doc, start_date, end_date)


def _run_project_handler(operation: str, doc: Document, *args) -> None:
	handlers = frappe.get_hooks("application_for_leave_project_handlers", default={})
	for path in handlers.get(operation, []):
		frappe.get_attr(path)(doc, *args)


def calculate_total_hours(doc: Document, start_date: date, end_date: date) -> None:
	worker = _validated_worker(doc)
	first_hours, last_hours = _leave_boundary_hours(doc)
	holiday_list, template, working_hours = _leave_calendar(worker, start_date, end_date)
	doc.lauser = worker.wuser

	holiday_dates = {
		getdate(row.holiday_date)
		for row in holiday_list.get("holidays", [])
		if row.get("holiday_date")
	}
	hours_by_date = {
		getdate(row.wht_date): flt(row.wht_hours)
		for row in working_hours.get("hod_working_hours_table", [])
		if row.get("wht_date")
	}
	default_hours = flt(template.get("hours_on_date")) or 8

	if start_date in holiday_dates:
		doc.alfrom_hours = 0
	if end_date in holiday_dates:
		doc.alto_hours = 0

	total_hours = 0.0
	for working_date in _dates_between(start_date, end_date):
		if working_date in holiday_dates:
			continue

		day_hours = hours_by_date.get(working_date, default_hours)
		if working_date == start_date:
			day_hours = min(first_hours, day_hours)
			doc.alfrom_hours = day_hours
		elif working_date == end_date:
			day_hours = min(last_hours, day_hours)
			doc.alto_hours = day_hours
		total_hours += day_hours

	doc.al_total_hours = total_hours


def validate_workflow_vote(doc: Document, next_state: str) -> None:
	"""Check current leave dependencies before a vote consumes the task."""
	if next_state not in (AFL_PENDING_STATE, AFL_APPROVED_STATE):
		return

	from dinext_common.workflow_approval.engine import WorkflowDomainRollbackError

	try:
		if next_state == AFL_APPROVED_STATE:
			_run_project_handler("validate_approval", doc)
			return

		start_date, end_date = _leave_dates(doc)
		worker = _validated_worker(doc)
		_leave_boundary_hours(doc)
		_leave_calendar(worker, start_date, end_date)
		_validate_overlap(doc, start_date, end_date)
	except (frappe.ValidationError, frappe.DoesNotExistError) as error:
		raise WorkflowDomainRollbackError(strip_html(str(error))) from error


def validate_leave_overlap(doc: Document) -> None:
	"""Reject overlapping dates before the workflow prepares a process."""
	_validate_overlap(doc, *_leave_dates(doc))


def _validate_overlap(doc: Document, start_date: date, end_date: date) -> None:
	if doc.get("docstatus") == 2:
		return

	# Serialize leave writes for this worker. Use a current read so a transaction
	# that waited for the Worker sees any leave saved by the prior transaction.
	_validated_worker(doc, for_update=True)
	filters = {
		"alworker": doc.alworker,
		"docstatus": ("!=", 2),
		"alfrom_date": ("<=", end_date),
		"alto_date": (">=", start_date),
	}
	if not doc.is_new():
		filters["name"] = ("!=", doc.name)

	if frappe.db.get_value("Application For Leave", filters, "name", for_update=True):
		frappe.throw(_("This Worker already has a leave application that overlaps the selected dates."))


def _leave_calendar(
	worker: Document, start_date: date, end_date: date
) -> tuple[Document, Document, Document]:
	worker_name = worker.name

	holiday_list_name = worker.get("wholiday_list")
	if not holiday_list_name:
		frappe.throw(
			_("Worker {0} has no Holiday List.").format(frappe.bold(worker_name))
		)
	holiday_list = frappe.get_doc("Holiday List", holiday_list_name)
	_validate_coverage(
		holiday_list,
		start_date,
		end_date,
		from_field="from_date",
		to_field="to_date",
		label=_("Holiday List"),
	)

	template_name = worker.get("wtimesheet_template")
	if not template_name:
		frappe.throw(
			_("Worker {0} has no Timesheet Template.").format(
				frappe.bold(worker_name)
			)
		)
	template = frappe.get_doc("Timesheet Template", template_name)

	working_hours_name = template.get("tt_working_hours_on_date")
	if not working_hours_name:
		frappe.throw(
			_("Timesheet Template {0} has no Working Hours On Date.").format(
				frappe.bold(template_name)
			)
		)
	working_hours = frappe.get_doc("Working Hours On Date", working_hours_name)
	_validate_coverage(
		working_hours,
		start_date,
		end_date,
		from_field="hod_from_date",
		to_field="hod_to_date",
		label=_("Working Hours On Date"),
	)

	return holiday_list, template, working_hours


def _validated_worker(doc: Document, *, for_update: bool = False) -> Document:
	worker_name = doc.get("alworker")
	if not worker_name:
		frappe.throw(_("Worker is required."))

	worker = frappe.get_doc("Worker", worker_name, for_update=for_update)
	worker_user = worker.get("wuser")
	if not worker_user:
		frappe.throw(_("Worker {0} has no user.").format(frappe.bold(worker_name)))
	if doc.get("lauser") and doc.lauser != worker_user:
		frappe.throw(_("User must match the selected Worker's user."))
	return worker


def _leave_boundary_hours(doc: Document) -> tuple[float, float]:
	first_hours = flt(doc.get("alfrom_hours"))
	last_hours = flt(doc.get("alto_hours"))
	if first_hours < 0 or last_hours < 0:
		frappe.throw(_("Leave hours cannot be negative."))
	return first_hours, last_hours


def _leave_dates(doc: Document) -> tuple[date, date]:
	if not doc.get("alfrom_date") or not doc.get("alto_date"):
		frappe.throw(_("Start and end dates are required."))

	start_date = getdate(doc.alfrom_date)
	end_date = getdate(doc.alto_date)
	if start_date > end_date:
		frappe.throw(_("Start date cannot be after end date."))
	return start_date, end_date


def _validate_coverage(
	coverage_doc: Document,
	start_date: date,
	end_date: date,
	*,
	from_field: str,
	to_field: str,
	label: str,
) -> None:
	coverage_start = coverage_doc.get(from_field)
	coverage_end = coverage_doc.get(to_field)
	if (
		not coverage_start
		or not coverage_end
		or getdate(coverage_start) > start_date
		or getdate(coverage_end) < end_date
	):
		frappe.throw(
			_("{0} {1} does not cover the leave period.").format(
				label,
				frappe.bold(coverage_doc.name),
			)
		)


def _dates_between(start_date: date, end_date: date):
	current_date = start_date
	while current_date <= end_date:
		yield current_date
		current_date += timedelta(days=1)
