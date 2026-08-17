"""UT / UTP ownership and period fields (ISS-2026-00926 phase 2).

Ports demodev Server Scripts:
- UT_Set_User_Group (User Timesheet, Before Save)
- UTP_Set_User_Group (User Timesheet Position, Before Save)
- User_Equals_Owner (User Timesheet Position, Before Insert)
- Timesheet_Position_Period (User Timesheet Position, Before Insert)
"""

from __future__ import annotations

import frappe
from frappe.utils import getdate


def set_ut_user_group(doc) -> None:
	"""Fill user_group from Worker when empty (ISS-2025-00955)."""
	if not (doc.timesheet_from and not doc.user_group):
		return
	worker = frappe.db.get_value(
		"Worker",
		{"wuser": doc.timesheet_from},
		["name", "wuser_group"],
		as_dict=True,
	)
	if worker and worker.wuser_group:
		doc.user_group = worker.wuser_group


def set_utp_user_group(doc) -> None:
	"""Fill UTP user_group from Worker when empty (ISS-2025-00955)."""
	if not (doc.user and not doc.user_group):
		return
	worker = frappe.db.get_value(
		"Worker",
		{"wuser": doc.user},
		["name", "wuser_group"],
		as_dict=True,
	)
	if worker and worker.wuser_group:
		doc.user_group = worker.wuser_group


def set_utp_owner_from_user(doc) -> None:
	"""Set owner = user on insert (ISS-2025-01319)."""
	if doc.user:
		doc.owner = doc.user


def set_utp_period(doc) -> None:
	"""Derive period label from parent User Timesheet dates (ISS-2025-01841)."""
	user_timesheet = (
		frappe.get_doc("User Timesheet", doc.user_timesheet)
		if doc.get("user_timesheet")
		else None
	)

	if not user_timesheet:
		frappe.msgprint("Табель пользователя не найден")
		return

	ts_valid_from = user_timesheet.get("ts_valid_from")
	ts_valid_for = user_timesheet.get("ts_valid_for")

	if not ts_valid_from or not ts_valid_for:
		frappe.msgprint("Одно из полей даты пустое")
		return

	date_from = getdate(ts_valid_from)
	date_for = getdate(ts_valid_for)
	delta_days = (date_for - date_from).days

	if delta_days <= 7:
		week_number = date_from.isocalendar()[1]
		month_number = date_from.month
		doc.period = f"{date_from.year}-{month_number:02d}-{week_number:02d}"
	elif 14 <= delta_days <= 16:
		month_number = date_from.month
		doc.period = (
			f"{date_from.year}-{month_number:02d}-I"
			if date_for.day <= 15
			else f"{date_from.year}-{month_number:02d}-II"
		)
	elif 28 <= delta_days <= 31:
		month_number = date_from.month
		doc.period = f"{date_from.year}-{month_number:02d}"
	else:
		frappe.msgprint("Разница в днях не соответствует заданным условиям")
