"""User Timesheet Position utilized hours (ISS-2026-00926 phase 2).

Port of demodev Server Script ``Utilization_Hours_V2`` (Before Save on
User Timesheet Position). Original ticket: ISS-2025-01841.
"""

from __future__ import annotations

import frappe
from frappe.utils import flt, formatdate, get_last_day, getdate

from project_workload_assignment.project_workload_assignment.project_workload.team_report.chart_aggregates import (
	_resolve_plan_year_month,
)

logger = frappe.logger("user_timesheet")


def apply_utilization_hours(doc) -> None:
	"""Apply project utilization rules to ``doc.table`` utilized_hours."""
	old_doc = doc.get_doc_before_save()
	if not (
		doc.get("project")
		and doc.get("table")
		and (not old_doc or old_doc.status in (None, "Редактирование"))
	):
		return

	project = frappe.get_cached_doc("Project", doc.project)
	if not project.get("custom_project_utilization"):
		return

	fy_cache: dict = {}
	for row in doc.table:
		if not row.date:
			continue

		row_date = getdate(row.date)
		if not row_date:
			continue

		closest_record = _find_closest_utilization(project.custom_project_utilization, row_date)
		if not closest_record:
			continue

		row_hours = flt(row.hours)
		row_utilized = flt(row.utilized_hours or 0)
		pu_included = closest_record.get("pu_included")

		if pu_included == "Да":
			if row_hours > 0 and row_utilized != row_hours:
				row.utilized_hours = row.hours
		elif pu_included == "В рамках плана":
			_apply_within_plan(doc, row, row_date, closest_record, fy_cache)
		else:
			if row_utilized != 0:
				row.utilized_hours = 0


def _find_closest_utilization(utilization_rows, row_date):
	closest_record = None
	for utilization in utilization_rows:
		if not utilization.pu_valid_from:
			continue
		pu_date = getdate(utilization.pu_valid_from)
		if not pu_date or pu_date > row_date:
			continue
		closest_pu_date = (
			getdate(closest_record.pu_valid_from) if closest_record else None
		)
		if not closest_record or (closest_pu_date and pu_date > closest_pu_date):
			closest_record = utilization
	return closest_record


def _apply_within_plan(doc, row, row_date, closest_record, fy_cache):
	is_monthly = closest_record.get("pu_limit") == "В месяц"
	planned_task, planned_amounts = _find_planned_task_and_amounts(
		doc, row_date, is_monthly, fy_cache
	)

	plan_hours = _plan_hours(planned_task, planned_amounts, is_monthly)
	tasks_for_fact = _tasks_for_fact_collection(doc, planned_task)
	actual_hours = _collect_actual_hours(doc, tasks_for_fact, row_date, is_monthly)

	remaining_hours = flt(plan_hours) - flt(actual_hours)
	logger.debug(
		"utilization plan=%s actual=%s remaining=%s monthly=%s",
		plan_hours,
		actual_hours,
		remaining_hours,
		is_monthly,
	)
	_distribute_remaining_hours(doc, remaining_hours)


def _find_planned_task_and_amounts(doc, row_date, is_monthly, fy_cache):
	planned_task = None
	planned_amounts = []
	current_task = doc.document_name

	while current_task is not None and not planned_task:
		pwe_list = frappe.get_all(
			"Project Work Efforts",
			filters={
				"pwe_project": doc.project,
				"pwe_task": current_task,
				"pwe_project_role": doc.project_role,
			},
			fields=["name"],
			limit=1,
		)
		if pwe_list:
			pwe = frappe.get_cached_doc("Project Work Efforts", pwe_list[0]["name"])
			for amount in pwe.pwe_amount:
				if is_monthly:
					resolved = _resolve_plan_year_month(
						amount.pwea_year, amount.pwea_month, fy_cache
					)
					if (
						resolved
						and resolved[0] == row_date.year
						and resolved[1] == row_date.month
						and flt(amount.pwea_plan or 0) > 0
					):
						planned_task = current_task
						planned_amounts = [amount]
						break
				elif flt(amount.pwea_plan or 0) > 0:
					planned_task = current_task
					planned_amounts.append(amount)

		if not planned_task:
			parent = frappe.db.get_value("Task", current_task, "parent_task")
			current_task = parent if parent else None

	return planned_task, planned_amounts


def _plan_hours(planned_task, planned_amounts, is_monthly):
	if not planned_task:
		return 0.0
	if is_monthly:
		if planned_amounts:
			return flt(planned_amounts[0].pwea_plan or 0)
		return 0.0
	return sum(flt(amount.pwea_plan or 0) for amount in planned_amounts)


def _tasks_for_fact_collection(doc, planned_task):
	root_task = planned_task if planned_task is not None else doc.document_name
	tasks_for_fact = []
	tasks_to_process = [root_task]
	while tasks_to_process:
		current_task = tasks_to_process.pop()
		tasks_for_fact.append(current_task)
		children = frappe.get_all(
			"Task",
			filters={"parent_task": current_task, "project": doc.project},
			fields=["name"],
		)
		tasks_to_process.extend(child["name"] for child in children)
	return tasks_for_fact


def _collect_actual_hours(doc, tasks_for_fact, row_date, is_monthly):
	if not tasks_for_fact:
		return 0.0

	utp_filters = {
		"document_name": ["in", tasks_for_fact],
		"project_role": doc.project_role,
		"name": ["!=", doc.name],
	}
	if is_monthly:
		first_day = formatdate(f"{row_date.year}-{row_date.month:02d}-01", "yyyy-MM-dd")
		last_day = get_last_day(row_date)
		utp_filters["ut_valid_from"] = ["between", [first_day, last_day]]

	actual_hours = 0.0
	for utp in frappe.db.get_all("User Timesheet Position", filters=utp_filters, fields=["name"]):
		utp_doc = frappe.get_cached_doc("User Timesheet Position", utp["name"])
		for ts_row in utp_doc.table:
			if not ts_row.date:
				continue
			ts_date = getdate(ts_row.date)
			if not ts_date:
				continue
			if is_monthly and (
				ts_date.month != row_date.month or ts_date.year != row_date.year
			):
				continue
			actual_hours += flt(ts_row.utilized_hours or 0)
	return actual_hours


def _distribute_remaining_hours(doc, remaining_hours):
	if remaining_hours > 0:
		valid_rows = []
		for r in doc.table:
			if not r.date:
				continue
			date_val = getdate(r.date)
			if date_val:
				valid_rows.append({"row": r, "date": date_val})

		valid_rows.sort(key=lambda x: x["date"])
		for item in valid_rows:
			r = item["row"]
			if remaining_hours <= 0:
				r.utilized_hours = 0.0
				continue

			hours = flt(r.hours or 0)
			if hours <= remaining_hours:
				r.utilized_hours = hours
				remaining_hours -= hours
			else:
				r.utilized_hours = remaining_hours
				remaining_hours = 0.0
	else:
		for r in doc.table:
			r.utilized_hours = 0.0
