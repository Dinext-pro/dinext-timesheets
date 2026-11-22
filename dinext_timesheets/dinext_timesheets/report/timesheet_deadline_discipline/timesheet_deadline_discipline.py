# Copyright (c) 2026, Dinext and contributors
# For license information, please see license.txt

# import frappe


def execute(filters=None):
	import frappe
	from frappe import _

	from dinext_timesheets.submission_discipline import overdue_chart, summary

	result = summary(filters)
	data = result["rows"]
	for row in data:
		row["submission_status_label"] = _(row["submission_status"])
	columns = [
		dict(fieldname=field, label=_(label), fieldtype=kind, width=width, **extra)
		for field, label, kind, width, extra in [
			("timesheet", "Timesheet", "Link", 210, {"options": "User Timesheet"}),
			("author_name", "Author", "Data", 180, {}),
			("period_from", "From Date", "Date", 110, {}),
			("period_to", "To Date", "Date", 110, {}),
			("submission_deadline", "Submission Deadline", "Date", 140, {}),
			("submitted_at", "First Complete Submission", "Datetime", 190, {}),
			("submission_status_label", "Submission Discipline", "Data", 170, {}),
			("resubmissions", "Resubmissions", "Int", 125, {}),
			("approval_percent", "On-time approvals, %", "Percent", 160, {}),
			("overdue_positions", "Overdue Positions", "Int", 145, {}),
			("pending_hours", "Hours awaiting approval", "Float", 180, {}),
		]
	]
	summaries = [
		dict(
			label=_(label),
			value=result[key] if result[key] is not None else _("No observations"),
			datatype="Percent" if key.endswith("percent") else "Float",
			indicator="Blue",
		)
		for label, key in [
			("On-time Timesheet Submissions", "submission_percent"),
			("On-time Timesheet Approvals", "approval_percent"),
			("Overdue Timesheet Approvals", "overdue_timesheets"),
			("Overdue Timesheet Positions", "overdue_positions"),
			("Hours awaiting approval", "pending_hours"),
		]
	]
	return columns, data, None, overdue_chart(result, (filters or {}).get("chart_metric", "Approval")), summaries


def execute_snapshot_report(filters: dict | None = None):
	"""Return columns and data for the report.

	This is the main entry point for snapshot report. When 'Synced
	Report' is enabled in report, framework will call this method
	every time the report is refreshed or a filter is updated. It
	accepts the same filters as normal execute. But a utility method -
	get_latest_sync, is also imported.

	"""
	return execute(filters)
