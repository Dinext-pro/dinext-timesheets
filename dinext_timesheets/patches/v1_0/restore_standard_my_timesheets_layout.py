"""Restore the shipped My Timesheets layout on sites with the earlier standard layout."""

import json
from pathlib import Path

import frappe
from frappe.utils import strip_html

WORKSPACE = "My Timesheets"
TABLES = {"number_cards": "number_card_name", "charts": "chart_name", "shortcuts": "label"}
WIDGET_KEYS = {"number_card": "number_card_name", "chart": "chart_name", "shortcut": "shortcut_name"}


def _key(block):
	kind = block["type"]
	data = block["data"]
	if kind == "header":
		title = strip_html(data["text"]).strip()
		if title == "Мои Таймшиты":
			title = WORKSPACE
		return kind, title
	return kind, data.get(WIDGET_KEYS.get(kind))


def _is_earlier_standard(workspace, standard, before, expected):
	if workspace.links or workspace.custom_blocks or workspace.quick_lists:
		return False
	if not set(map(_key, before)).issubset(map(_key, expected)):
		return False
	for table, field in TABLES.items():
		present = {row.get(field) for row in workspace.get(table)}
		allowed = {row[field] for row in standard[table]}
		if not present.issubset(allowed):
			return False
		if table == "number_cards" and len(allowed - present) != 6:
			return False
		if table == "shortcuts" and len(allowed - present) != 2:
			return False
	return True


def execute():
	if not frappe.db.exists("Workspace", WORKSPACE):
		return

	workspace = frappe.get_doc("Workspace", WORKSPACE)
	if not workspace.public or workspace.for_user or workspace.module != "Dinext Timesheets":
		return

	default_path = frappe.get_app_path(
		"dinext_timesheets", "dinext_timesheets", "workspace", "my_timesheets", "my_timesheets.json"
	)
	standard = json.loads(Path(default_path).read_text(encoding="utf-8"))
	before = json.loads(workspace.content)
	expected = json.loads(standard["content"])

	if not _is_earlier_standard(workspace, standard, before, expected):
		return

	workspace.content = standard["content"]
	for table in TABLES:
		workspace.set(table, standard[table])
	workspace.save(ignore_permissions=True)
