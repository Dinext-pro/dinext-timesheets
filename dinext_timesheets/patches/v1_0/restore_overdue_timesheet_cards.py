# ruff: noqa: RUF001 -- Russian workspace and card labels are intentional.
"""Restore the personal overdue card and add the submission count in Deadline Control."""

import frappe
from frappe.utils import strip_html

PERSONAL_LABEL = "Overdue Timesheets"
PERSONAL_NAME = "Мои просроченные таймшиты"
OVERALL_NAME = "Timesheets Overdue for Submission"
APPROVED_LABELS = {"Approved Timesheets", "тш согласовано", "Мои согласованные таймшиты"}
REJECTED_LABELS = {"Rejected Timesheets", "тш отклонено", "Мои отклоненные таймшиты"}
OVERDUE_LABELS = {PERSONAL_LABEL, PERSONAL_NAME, "тш просрочено", OVERALL_NAME}


def _is_card(block, labels):
	return block["type"] == "number_card" and block["data"].get("number_card_name") in labels


def _is_header(block, labels):
	return block["type"] == "header" and strip_html(block["data"].get("text", "")).strip() in labels


def _card_block(block_id, label):
	return {"id": block_id, "type": "number_card", "data": {"col": 4, "number_card_name": label}}


def place_overdue_cards(blocks):
	updated = [block for block in blocks if not _is_card(block, OVERDUE_LABELS)]
	personal_index = next(
		(i for i, block in enumerate(updated) if _is_card(block, APPROVED_LABELS)), None
	)
	if personal_index is None:
		personal_index = next(
			(i + 1 for i, block in enumerate(updated) if _is_card(block, REJECTED_LABELS)), None
		)
	if personal_index is None:
		return blocks

	updated.insert(personal_index, _card_block("X3L9ekhaMv", PERSONAL_LABEL))
	deadline_index = next(
		(
			i for i, block in enumerate(updated)
			if block["type"] == "header"
			and (block["id"] == "deadline-control" or _is_header(block, {"Deadline Control", "Контроль сроков"}))
		),
		None,
	)
	if deadline_index is None:
		deadline_index = next(
			(i for i, block in enumerate(updated) if _is_header(block, {"Timesheet Reports", "Отчетность"})),
			len(updated),
		)
		updated.insert(deadline_index, {
			"id": "deadline-control",
			"type": "header",
			"data": {"col": 12, "text": '<span class="h4"><b>Deadline Control</b></span>'},
		})
	updated.insert(deadline_index + 1, _card_block("deadline-overdue-submission", OVERALL_NAME))
	return updated


def execute():
	if not frappe.db.exists("Workspace", "My Timesheets"):
		return

	workspace = frappe.get_doc("Workspace", "My Timesheets")
	before = frappe.parse_json(workspace.content or "[]")
	after = place_overdue_cards(before)
	if not any(_is_card(block, {OVERALL_NAME}) for block in after):
		return

	changed = after != before
	if changed:
		workspace.content = frappe.as_json(after)

	for name, label in ((PERSONAL_NAME, PERSONAL_LABEL), (OVERALL_NAME, OVERALL_NAME)):
		if not frappe.db.exists("Number Card", name):
			frappe.reload_doc("dinext_timesheets", "number_card", frappe.scrub(name), force=True)
		link = next((row for row in workspace.number_cards if row.number_card_name == name), None)
		if link is None:
			workspace.append("number_cards", {"number_card_name": name, "label": label})
			changed = True
		elif link.label != label:
			link.label = label
			changed = True

	if changed:
		workspace.save(ignore_permissions=True)
