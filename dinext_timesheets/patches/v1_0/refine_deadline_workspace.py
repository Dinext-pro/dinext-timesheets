"""Organize owned deadline blocks while preserving unrelated workspace content."""

import frappe

CARDS = {
	"Overdue Timesheets",
	"Мои просроченные таймшиты",
	"On-time Timesheet Submissions",
	"On-time Timesheet Approvals",
	"Overdue Timesheet Approvals",
	"Overdue Timesheet Positions",
	"Timesheet Hours Awaiting Approval",
}
CHARTS = ("Overdue Timesheet Submissions by Author", "Overdue Timesheet Approvals by Approver")


def arrange(blocks):
	cards = [b for b in blocks if b["type"] == "number_card" and b["data"].get("number_card_name") in CARDS]
	reports = [
		b
		for b in blocks
		if b["type"] == "shortcut" and b["data"].get("shortcut_name") == "Timesheet Deadline Discipline"
	]
	owned = {
		"deadline-spacer",
		"deadline-control",
		"deadline-control-spacer",
		"deadline-chart-0",
		"deadline-chart-1",
	}
	rest = [b for b in blocks if b not in cards + reports and b.get("id") not in owned]
	report_index = next(
		(
			i
			for i, b in enumerate(rest)
			if b["type"] == "header" and "Timesheet Reports" in b["data"].get("text", "")
		),
		None,
	)
	if report_index is None:
		return blocks
	rest[report_index:report_index] = [
		{
			"id": "deadline-control",
			"type": "header",
			"data": {"col": 12, "text": '<span class="h4"><b>Deadline Control</b></span>'},
		},
		*cards,
		*[
			{"id": f"deadline-chart-{i}", "type": "chart", "data": {"col": 6, "chart_name": name}}
			for i, name in enumerate(CHARTS)
		],
		{"id": "deadline-control-spacer", "type": "spacer", "data": {"col": 12}},
	]
	config_index = next(
		(
			i
			for i, b in enumerate(rest)
			if b["type"] == "header" and "Timesheet Configuration" in b["data"].get("text", "")
		),
		len(rest),
	)
	if config_index and rest[config_index - 1]["type"] == "spacer":
		config_index -= 1
	rest[config_index:config_index] = reports
	return rest


def execute():
	if not frappe.db.exists("Workspace", "My Timesheets"):
		return
	workspace = frappe.get_doc("Workspace", "My Timesheets")
	workspace.content = frappe.as_json(arrange(frappe.parse_json(workspace.content)))
	for name in CHARTS:
		if frappe.db.exists("Dashboard Chart", name):
			chart = frappe.get_doc("Dashboard Chart", name)
			if chart.chart_type == "Report" and chart.report_name == "Timesheet Deadline Discipline":
				chart.db_set("currency", None, update_modified=False)
		if frappe.db.exists("Dashboard Chart", name) and not any(
			row.chart_name == name for row in workspace.charts
		):
			workspace.append("charts", {"chart_name": name, "label": name})
	workspace.save(ignore_permissions=True)
