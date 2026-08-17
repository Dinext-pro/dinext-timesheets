"""UT / UTP hour aggregates (ISS-2026-00926 phase 2).

Ports demodev Server Scripts:
- UT_Hours_Calculate_V4 (User Timesheet, Before Save)
- All_Hours_Calculate (User Timesheet Position, Before Save)
"""

from __future__ import annotations

import frappe
from frappe.utils import add_days, date_diff, flt, getdate


# Worker fieldname uses Cyrillic «с» (U+0441) — keep as in DocType / demodev SS.
_COST_NORMALIZATION = "сost_normalization"


def calculate_ut_hours(doc) -> None:
	"""Sum position hours and schedule/leave/utilization plan on User Timesheet."""
	total_worked = 0.0
	total_utilized = 0.0

	positions = frappe.get_all(
		"User Timesheet Position",
		filters={"user_timesheet": doc.name},
		fields=["name"],
	)

	for pos in positions:
		pos_doc = frappe.get_doc("User Timesheet Position", pos.name)
		for d in pos_doc.get("table", []):
			total_worked += flt(d.hours)
			total_utilized += flt(d.utilized_hours)

	doc.total_hours_worked = total_worked
	doc.total_hours_utilized = total_utilized

	worker = frappe.get_doc("Worker", {"wuser": doc.timesheet_from})
	hol_list = frappe.get_doc("Holiday List", worker.wholiday_list)

	if date_diff(doc.ts_valid_from, hol_list.from_date) < 0 or date_diff(
		hol_list.to_date, doc.ts_valid_for
	) < 0:
		frappe.throw(
			"Holiday List "
			+ worker.wholiday_list
			+ " is not active for the whole timesheet period"
		)

	holidays = {getdate(h.holiday_date) for h in hol_list.get("holidays", [])}

	tmpl = frappe.get_doc("Timesheet Template", worker.wtimesheet_template)
	standard_hours = flt(tmpl.hours_on_date)

	wod = {}
	if tmpl.tt_working_hours_on_date:
		wod = frappe.get_doc("Working Hours On Date", tmpl.tt_working_hours_on_date)
		if date_diff(doc.ts_valid_from, wod.hod_from_date) < 0 or date_diff(
			wod.hod_to_date, doc.ts_valid_for
		) < 0:
			frappe.throw(
				"Working Hours On Date "
				+ tmpl.tt_working_hours_on_date
				+ " is not active for the whole timesheet period"
			)

	override_hours = {
		getdate(r.wht_date): flt(r.wht_hours)
		for r in wod.get("hod_working_hours_table", [])
	}

	leave_apps = frappe.get_all(
		"Application For Leave",
		filters={"lauser": doc.timesheet_from, "status": "Согласовано"},
		fields=[
			"alfrom_date",
			"alto_date",
			"alfrom_hours",
			"alto_hours",
			"altype_of_leave",
		],
	)

	total_leave = 0.0
	total_util_leave = 0.0
	total_utilization_plan = 0.0
	total_schedule = 0.0
	days_count = date_diff(doc.ts_valid_for, doc.ts_valid_from) + 1

	for i in range(days_count):
		day = getdate(add_days(doc.ts_valid_from, i))
		if day in holidays:
			continue

		scheduled = override_hours.get(day, standard_hours)
		total_schedule += scheduled

		valid_utils = [
			u
			for u in worker.get("utilization", [])
			if date_diff(u.util_valid_from, day) <= 0
		]

		absence_hours = 0.0
		for app in leave_apps:
			start = max(getdate(app.alfrom_date), getdate(doc.ts_valid_from))
			end = min(getdate(app.alto_date), getdate(doc.ts_valid_for))
			if date_diff(day, start) < 0 or date_diff(day, end) > 0:
				continue

			span = date_diff(end, start) + 1
			offset = date_diff(day, start)

			if offset == 0 and flt(app.alfrom_hours) > 0:
				hrs = flt(app.alfrom_hours)
			elif offset == span - 1 and span > 1 and flt(app.alto_hours) > 0:
				hrs = flt(app.alto_hours)
			else:
				hrs = override_hours.get(day, standard_hours)

			total_leave += hrs
			if app.altype_of_leave != "Отгул":
				absence_hours += hrs
				total_util_leave += hrs

		planned_work = max(0, scheduled - absence_hours)

		if valid_utils:
			latest_util = max(valid_utils, key=lambda u: getdate(u.util_valid_from))
			pct = flt(latest_util.utilization) / 100.0
		else:
			pct = 0.0

		total_utilization_plan += planned_work * pct

	doc.total_hours_schedule = total_schedule
	doc.total_hours_leave = total_leave
	doc.total_hours_util_leave = total_util_leave
	doc.utilization_hours_plan = total_utilization_plan

	if total_utilization_plan > 0:
		doc.utilization_fulfillment = 100 * (
			1 + (total_utilized - total_utilization_plan) / total_utilization_plan
		)

	doc.total_hours_to_work = max(0, doc.total_hours_schedule - doc.total_hours_util_leave)

	if doc.total_hours_to_work > 0:
		doc.utilization = flt(doc.total_hours_utilized) / flt(doc.total_hours_to_work) * 100
	else:
		doc.utilization = 0.0

	# ISS-2025-00896 — fieldname is Cyrillic «с» + ost_normalization
	if getattr(worker, _COST_NORMALIZATION, None) == "Равномерно" and doc.total_hours_worked > 0:
		doc.normalization = min(1, doc.total_hours_to_work / doc.total_hours_worked)
	else:
		doc.normalization = 1


def calculate_utp_all_hours(doc) -> None:
	"""Sum row.hours into all_hours when position is editable."""
	if doc.status in ("Черновик", "Редактирование"):
		doc.all_hours = sum(row.hours for row in doc.table) if doc.table else 0
