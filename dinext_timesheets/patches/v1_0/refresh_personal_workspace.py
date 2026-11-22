# ruff: noqa: RUF001 -- Russian workspace and card labels are intentional.
"""Add the expense total and arrange shortcuts in their own workspace sections."""

import frappe
from frappe.utils import strip_html

EXPENSE_TOTAL = "Всего заявок на расходы"
SETTINGS = "Timesheet Settings"


def execute():
	if not frappe.db.exists("Workspace", "Мои Таймшиты"):
		return
	if not frappe.db.exists("Number Card", EXPENSE_TOTAL):
		frappe.reload_doc("dinext_projects_pl", "number_card", frappe.scrub(EXPENSE_TOTAL))
	workspace = frappe.get_doc("Workspace", "Мои Таймшиты")
	before = workspace.as_dict()
	blocks = frappe.parse_json(workspace.content)
	headers = {
		strip_html(block["data"]["text"]).strip(): block for block in blocks if block["type"] == "header"
	}
	if expense_header := headers.get("Мои Заявки на расходы"):
		start = blocks.index(expense_header) + 1
		if not any(row.number_card_name == EXPENSE_TOTAL for row in workspace.number_cards):
			workspace.append("number_cards", {"number_card_name": EXPENSE_TOTAL, "label": EXPENSE_TOTAL})
		if not any(block["data"].get("number_card_name") == EXPENSE_TOTAL for block in blocks):
			blocks.insert(
				start,
				{
					"id": "expenseTotal",
					"type": "number_card",
					"data": {"number_card_name": EXPENSE_TOTAL, "col": 3},
				},
			)
		for block in blocks[start:]:
			if block["type"] != "number_card":
				break
			block["data"]["col"] = 3

	if "Отчетность" in headers and "Настройки" in headers:
		_align_shortcuts(workspace, blocks, headers["Отчетность"], headers["Настройки"])

	if blocks != frappe.parse_json(workspace.content):
		workspace.content = frappe.as_json(blocks, indent=None, separators=(",", ":"), ensure_ascii=False)
	if workspace.as_dict() != before:
		workspace.save(ignore_permissions=True)


def _align_shortcuts(workspace, blocks, reports, settings):
	report_labels = ("Мои списания по ТШ", "Отчетность по ТШ", "Отчет по утилизации", "Календарь отсутствий")
	setting_labels = (SETTINGS, "Timesheet Template", "Worker", "Holiday List", "Working Hours On Date")

	if not any(row.link_to == SETTINGS and row.type == "DocType" for row in workspace.shortcuts):
		workspace.append("shortcuts", {"label": SETTINGS, "type": "DocType", "link_to": SETTINGS})

	shortcuts = {
		block["data"]["shortcut_name"]: block
		for block in blocks
		if block["type"] == "shortcut" and block["data"]["shortcut_name"] in report_labels + setting_labels
	}
	if SETTINGS not in shortcuts:
		shortcuts[SETTINGS] = {
			"id": "TPod0jvW6v",
			"type": "shortcut",
			"data": {"shortcut_name": SETTINGS},
		}
	for block in shortcuts.values():
		block["data"]["col"] = 4
	reports["data"]["col"] = settings["data"]["col"] = 12

	blocks[:] = [
		block
		for block in blocks
		if block != settings and block not in shortcuts.values() and block.get("id") != "rl1YpJ1xc3"
	]
	start = blocks.index(reports) + 1
	blocks[start:start] = [
		*(shortcuts[label] for label in report_labels if label in shortcuts),
		{"id": "rl1YpJ1xc3", "type": "spacer", "data": {"col": 12}},
		settings,
		*(shortcuts[label] for label in setting_labels if label in shortcuts),
	]
