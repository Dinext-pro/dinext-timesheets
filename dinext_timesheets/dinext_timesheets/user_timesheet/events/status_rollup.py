"""UTP → User Timesheet status rollup + Task act dates.

Port of Server Script ``UTP_UT_Status_V3`` (After Save on User Timesheet Position).
Tickets: ISS-2025-02143, ISS-2025-02606, ISS-2026-00926, ISS-2026-03288 (layer 3 cutover).
"""

from __future__ import annotations

import frappe
from frappe.utils import flt, getdate, nowdate


def rollup_ut_status_and_task_dates(doc) -> None:
	old_doc = doc.get_doc_before_save()
	old_status = old_doc.status if old_doc and old_doc.status else None

	entered_approved = doc.status == "Согласовано" and old_status != "Согласовано"
	left_approved = old_status == "Согласовано" and doc.status != "Согласовано"

	if doc.status == "Отклонено":
		_set_ut_status(doc.user_timesheet, "Отклонено")
	elif doc.status == "Согласовано":
		_maybe_approve_ut(doc.user_timesheet)
	elif doc.status == "Редактирование":
		_maybe_rework_ut(doc, old_doc)

	if doc.document_type == "Task" and doc.document_name and (
		entered_approved or left_approved
	):
		_update_task_act_dates(doc)


def _set_ut_status(ut_name, status, approval_date=None) -> None:
	user_timesheet = frappe.get_doc("User Timesheet", ut_name)
	user_timesheet.ut_status = status
	if approval_date is not None:
		user_timesheet.ut_approval_date = approval_date
	user_timesheet.save(ignore_permissions=True)


def _maybe_approve_ut(ut_name) -> None:
	pending = frappe.get_all(
		"User Timesheet Position",
		filters={"user_timesheet": ut_name, "status": ["!=", "Согласовано"]},
		ignore_permissions=True,
	)
	if pending:
		return

	user_timesheet = frappe.get_doc("User Timesheet", ut_name)
	if user_timesheet.ut_status == "Согласован":
		return

	user_timesheet.ut_status = "Согласован"
	user_timesheet.ut_approval_date = nowdate()
	user_timesheet.save(ignore_permissions=True)


def _maybe_rework_ut(doc, old_doc) -> None:
	# ISS-2025-02143
	if not (old_doc and old_doc.status and old_doc.status != "Редактирование"):
		return

	ut = doc.user_timesheet
	user_timesheet = frappe.get_doc("User Timesheet", ut)
	if user_timesheet.ut_status == "На доработке":
		return

	positions = frappe.get_all(
		"User Timesheet Position",
		filters={"user_timesheet": ut},
		fields=["name"],
		ignore_permissions=True,
	)
	for position in positions:
		frappe.db.set_value(
			"User Timesheet Position",
			position.name,
			{"status": "Редактирование", "workflow_state": "Редактирование"},
		)

	user_timesheet.ut_status = "На доработке"
	user_timesheet.save(ignore_permissions=True)


def _update_task_act_dates(doc) -> None:
	approved_positions = frappe.get_all(
		"User Timesheet Position",
		filters={
			"document_type": "Task",
			"document_name": doc.document_name,
			"status": "Согласовано",
		},
		fields=["name"],
		ignore_permissions=True,
	)

	act_start_date = None
	act_end_date = None

	for approved_position in approved_positions:
		position_doc = frappe.get_doc("User Timesheet Position", approved_position.name)
		for row in position_doc.get("table", []):
			if not row.date:
				continue
			hours = flt(row.hours)
			if hours <= 0:
				continue
			row_date = getdate(row.date)
			if act_start_date is None or row_date < act_start_date:
				act_start_date = row_date
			if act_end_date is None or row_date > act_end_date:
				act_end_date = row_date

	task_doc = frappe.get_doc("Task", doc.document_name)

	if task_doc.completed_on:
		completed_on_date = getdate(task_doc.completed_on)
		if act_end_date is None or completed_on_date > act_end_date:
			act_end_date = completed_on_date

	curr_start = task_doc.act_start_date
	curr_end = task_doc.act_end_date
	new_start = act_start_date
	new_end = act_end_date
	protected_curr_start = curr_start
	protected_curr_end = curr_end
	issue_end = None

	if task_doc.get("type") == "Issue" and task_doc.get("custom_linked_issue"):
		issue_meta = frappe.get_meta("Issue")
		issue_resolution_field = None
		if issue_meta.has_field("resolution_date"):
			issue_resolution_field = "resolution_date"
		elif issue_meta.has_field("sla_resolution_date"):
			issue_resolution_field = "sla_resolution_date"

		issue_fields = ["opening_date"]
		if issue_resolution_field:
			issue_fields.append(issue_resolution_field)

		issue_dates = frappe.db.get_value(
			"Issue",
			task_doc.get("custom_linked_issue"),
			issue_fields,
			as_dict=True,
		)
		if issue_dates:
			issue_start = issue_dates.get("opening_date")
			issue_end = (
				issue_dates.get(issue_resolution_field) if issue_resolution_field else None
			)
			current_issue_start = "" if not curr_start else str(curr_start)
			current_issue_end = "" if not curr_end else str(curr_end)
			linked_issue_start = "" if not issue_start else str(issue_start)
			linked_issue_end = "" if not issue_end else str(getdate(issue_end))
			next_issue_start = "" if not new_start else str(new_start)
			next_issue_end = "" if not new_end else str(new_end)

			if (
				current_issue_start == linked_issue_start
				and current_issue_end == linked_issue_end
				and (
					next_issue_start != current_issue_start
					or next_issue_end != current_issue_end
				)
			):
				protected_curr_start = None
				protected_curr_end = None

	if issue_end:
		issue_end_date = getdate(issue_end)
		if act_end_date is None or issue_end_date > act_end_date:
			act_end_date = issue_end_date
			new_end = act_end_date

	allow_act_update = False
	if (not new_start) and (not new_end):
		allow_act_update = False
	elif (not protected_curr_start) and (not protected_curr_end):
		allow_act_update = True
	else:
		allow_act_update = True
		if protected_curr_start:
			if (not new_start) or getdate(new_start) > getdate(protected_curr_start):
				allow_act_update = False
		if protected_curr_end:
			if (not new_end) or getdate(new_end) < getdate(protected_curr_end):
				allow_act_update = False

	current_act_start = "" if not curr_start else str(curr_start)
	current_act_end = "" if not curr_end else str(curr_end)
	next_act_start = "" if not new_start else str(new_start)
	next_act_end = "" if not new_end else str(new_end)

	if allow_act_update and (
		current_act_start != next_act_start or current_act_end != next_act_end
	):
		if new_start is not None:
			task_doc.act_start_date = new_start
		if new_end is not None:
			task_doc.act_end_date = new_end
		# Save_PM_Only still runs on ignore_permissions; skip СПП gate for date sync.
		task_doc.flags.skip_pss_guard = True
		task_doc.save(ignore_permissions=True)
