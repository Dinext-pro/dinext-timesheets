"""Worker-calendar submission deadlines and read-time author overdue state."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

import frappe
from frappe import _
from frappe.utils import nowdate

LEGACY_STATUSES = {
	"Черновик": "Draft",
	"На доработке": "Rework",
	"Отклонено": "Rejected",
	"На согласовании": "Pending Approval",
	"Согласован": "Approved",
}
EDITABLE_STATUSES = ("Draft", "Rework")
AUTHOR_STATUSES = (*EDITABLE_STATUSES, "Rejected")
AUTHOR_QUERY_STATUSES = (*AUTHOR_STATUSES, "Черновик", "На доработке", "Отклонено")


class CalendarCoverageError(ValueError):
	def __init__(self, uncovered_date: date):
		self.uncovered_date = uncovered_date
		super().__init__(f"Calendar does not cover {uncovered_date}")


def _date(value) -> date:
	if isinstance(value, datetime):
		return value.date()
	return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


def validate_working_days(value) -> int:
	try:
		number = Decimal(str(value))
		if not number.is_finite() or number < 0 or number != number.to_integral_value():
			raise ValueError
		return int(number)
	except (ValueError, TypeError, InvalidOperation):
		raise ValueError("Working Days must be a non-negative integer") from None


def calculate_dispatch_date(period_end, working_days, calendar_from, calendar_to, holidays) -> date:
	"""Count calendar workdays after period end, bounded by the assigned calendar."""
	remaining = validate_working_days(working_days)
	current, first, last = _date(period_end), _date(calendar_from), _date(calendar_to)
	if not first <= current <= last:
		raise CalendarCoverageError(current)
	off_days = {_date(day) for day in holidays}
	while remaining:
		current += timedelta(days=1)
		if current > last:
			raise CalendarCoverageError(current)
		if current not in off_days:
			remaining -= 1
	return current


def is_timesheet_overdue(deadline, status, as_of=None) -> bool:
	if not deadline or LEGACY_STATUSES.get(status, status) not in AUTHOR_STATUSES:
		return False
	if as_of is None:
		from frappe.utils import nowdate

		as_of = nowdate()
	return _date(deadline) < _date(as_of)


def overdue_filters(user: str, as_of: str, statuses=AUTHOR_QUERY_STATUSES) -> list:
	return [
		["timesheet_from", "=", user],
		["ut_status", "in", list(statuses)],
		["ts_date_of_dispatch", "is", "set"],
		["ts_date_of_dispatch", "<", as_of],
	]


def prepare_dispatch_date(doc, method=None) -> None:
	"""Derive editable deadlines; never let non-editable saves replace their snapshot."""
	if LEGACY_STATUSES.get(doc.ut_status, doc.ut_status) not in EDITABLE_STATUSES:
		old = doc.get_doc_before_save()
		if old is not None:
			doc.ts_date_of_dispatch = old.ts_date_of_dispatch
		return
	if not doc.timesheet_from or not doc.ts_valid_for:
		frappe.throw(_("Timesheet author and period end are required to calculate the deadline"))
	worker_name = frappe.db.get_value("Worker", {"wuser": doc.timesheet_from}, "name")
	if not worker_name:
		frappe.throw(_("Timesheet owner has no Worker record"))
	worker = frappe.get_doc("Worker", worker_name)
	template_name = doc.ts_from_template or worker.wtimesheet_template
	if not template_name:
		frappe.throw(_("Worker has no Timesheet Template"))
	if not worker.wholiday_list:
		frappe.throw(_("Worker has no Holiday List"))
	template = frappe.get_doc("Timesheet Template", template_name)
	calendar = frappe.get_doc("Holiday List", worker.wholiday_list)
	try:
		doc.ts_date_of_dispatch = calculate_dispatch_date(
			doc.ts_valid_for,
			template.working_days,
			calendar.from_date,
			calendar.to_date,
			[row.holiday_date for row in calendar.get("holidays", [])],
		)
	except CalendarCoverageError as exc:
		frappe.throw(_("Holiday List {0} does not cover {1}; extend the worker calendar").format(
			calendar.name, exc.uncovered_date
		))
	except (ValueError, TypeError):
		frappe.throw(_("Working Days must be a non-negative integer"))


@frappe.whitelist()
def get_deadline_state(name: str) -> dict:
	"""Return current state without updating the document or the legacy flag."""
	doc = frappe.get_doc("User Timesheet", name)
	doc.check_permission("read")
	deadline = str(doc.ts_date_of_dispatch) if doc.ts_date_of_dispatch else None
	return {
		"deadline": deadline,
		"overdue": is_timesheet_overdue(deadline, doc.ut_status, nowdate()),
	}


@frappe.whitelist()
def get_my_overdue_summary(filters=None) -> dict:
	"""Number Card/Desk contract. Caller-supplied filters cannot change the owner."""
	today = nowdate()
	user = frappe.session.user
	# Select filters reject values absent from their options. Use this site's
	# status vocabulary for both count and navigation (English or legacy Russian).
	options = frappe.get_meta("User Timesheet").get_field("ut_status").options.splitlines()
	statuses = [status for status in options if status in AUTHOR_QUERY_STATUSES]
	rows = frappe.get_list(
		"User Timesheet",
		filters=overdue_filters(user, today, statuses),
		fields=["count(name) as total"],
		order_by=None,
	)
	return {
		"value": int(rows[0].total) if rows else 0,
		"route": ["List", "User Timesheet"],
		"route_options": {
			"timesheet_from": user,
			"ut_status": ["in", statuses],
			# ListView supports several comparisons for one field as JSON strings.
			"ts_date_of_dispatch": [json.dumps(["is", "set"]), json.dumps(["<", today])],
		},
	}
