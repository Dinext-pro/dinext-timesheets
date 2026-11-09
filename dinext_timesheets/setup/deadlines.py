"""Idempotent metadata cutover after fixture import; never saves timesheets."""

from __future__ import annotations

import re

import frappe

REMINDERS = ("Task_Timesheet_Overdue", "Issue_Timesheet_Overdue")
LEGACY_FORMS = (
	"User_Timesheet_Position_to_User_Timesheet_form_integration_V10",
	"User_Timesheet_Position_to_User_Timesheet_form_integration_V10_OLD",
)
NOTIFICATIONS = ("Таймшит не отправлен", "Таймшит не отправленМ")
NOTIFICATION_CONDITION = (
	"doc.ts_date_of_dispatch and doc.ut_status in "
	"('Draft', 'Rejected', 'Rework', 'Черновик', 'Отклонено', 'На доработке')"
)


def _update(doctype, name, values):
	if not frappe.db.exists(doctype, name):
		return
	current = frappe.db.get_value(doctype, name, list(values), as_dict=True)
	changed = {field: value for field, value in values.items() if current.get(field) != value}
	if changed:
		frappe.db.set_value(doctype, name, changed, update_modified=False)


def configure_deadline_metadata():
	for name in REMINDERS:
		_update("Client Script", name, {
			"enabled": 0,
			"script": "// Replaced by dinext_timesheets/public/js/timesheet_deadline_reminder.js\n",
		})
	for name in LEGACY_FORMS:
		if not frappe.db.exists("Client Script", name):
			continue
		script = frappe.db.get_value("Client Script", name, "script") or ""
		script = re.sub(
			r"(?m)^[ \t]*if\s*\(\s*frm\.doc\.is_overdue\b[^\n]*\)\s*\{\r?\n[^\n]*\r?\n[ \t]*\}\r?\n?",
			"", script,
		)
		script = re.sub(r"(?m)^[ \t]*(?:let|const|var) reporting_dispatch_period[^\n]*\n?", "", script)
		script = re.sub(r"(?m)^[ \t]*frm\.doc\.ts_date_of_dispatch\s*=[^\n]*\n?", "", script)
		_update("Client Script", name, {"enabled": 0, "script": script})
	_update("Server Script", "TSCrW2", {
		"disabled": 1,
		"script": "# Replaced by dinext_timesheets.dinext_timesheets.user_timesheet.scheduler\n",
	})
	_update("Number Card", "Мои просроченные таймшиты", {
		"type": "Custom", "method": "dinext_timesheets.deadlines.get_my_overdue_summary",
		"filters_json": "[]", "dynamic_filters_json": "[]", "show_percentage_stats": 0,
	})
	for name in NOTIFICATIONS:
		# Existing disabled records may have historical, missing Sender links.
		# Update only their inactive rule fields; preserve sender configuration.
		_update("Notification", name, {
			"enabled": 0, "date_changed": "ts_date_of_dispatch", "days_in_advance": 1,
			"condition": NOTIFICATION_CONDITION,
		})
	frappe.clear_cache(doctype="Client Script")
