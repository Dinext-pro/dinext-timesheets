# ruff: noqa: RUF001 -- Russian card names and stored workflow states are intentional.
"""Refresh status filters without replacing a site's newer deadline card."""

import json

import frappe


def execute():
	statuses = {
		"Моих таймшитов на редактировании": ["Draft", "Rework", "Черновик", "На доработке", "", None],
		"Моих таймшитов на согласовании": ["Pending Approval", "На согласовании"],
		"Мои отклоненные таймшиты": ["Rejected", "Отклонено"],
		"Мои согласованные таймшиты": ["Approved", "Согласован"],
	}
	for name, values in statuses.items():
		if not frappe.db.exists("Number Card", name):
			continue
		card = frappe.get_doc("Number Card", name)
		desired = json.dumps([["User Timesheet", "ut_status", "in", values]], ensure_ascii=False)
		if card.filters_json != desired:
			card.filters_json = desired
			card.save(ignore_permissions=True)
	name = "Мои просроченные таймшиты"
	if frappe.db.exists("Number Card", name):
		card = frappe.get_doc("Number Card", name)
		if card.type == "Document Type":
			card.filters_json = json.dumps(
				[
					[
						"User Timesheet",
						"ut_status",
						"in",
						["Draft", "Rework", "Rejected", "Черновик", "На доработке", "Отклонено", "", None],
					],
					["User Timesheet", "is_overdue", "=", 1],
				],
				ensure_ascii=False,
			)
			card.save(ignore_permissions=True)
