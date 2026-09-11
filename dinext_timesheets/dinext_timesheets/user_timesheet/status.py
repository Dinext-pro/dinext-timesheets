"""Set UT / UTP status (demodev SS Set Timesheet Status)."""

from __future__ import annotations

import json

import frappe

from .permissions import assert_can_set_timesheet_status


def _parse_positions(positions):
	if positions is None:
		positions = frappe.form_dict.get("positions")
	if isinstance(positions, str):
		positions = json.loads(positions) if positions else []
	if isinstance(positions, list):
		return positions
	return list(positions) if positions else []


def set_timesheet_status(positions=None, pos_status=None, ts_name=None, ts_status=None):
	"""Update UTP workflow/status; optionally parent UT status."""
	pos_status = pos_status if pos_status is not None else frappe.form_dict.get("pos_status")
	ts_name = ts_name if ts_name is not None else frappe.form_dict.get("ts_name")
	ts_status = ts_status if ts_status is not None else frappe.form_dict.get("ts_status")
	items = _parse_positions(positions)

	if not pos_status:
		frappe.throw(frappe._("pos_status is required"))

	assert_can_set_timesheet_status(items, ts_name, ts_status)

	updated = 0
	for p in items:
		name = p if isinstance(p, str) else p.get("name")
		if not name:
			continue
		position = frappe.get_doc("User Timesheet Position", name)
		position.status = pos_status
		position.workflow_state = pos_status
		position.save()
		updated += 1

	if ts_name and ts_status:
		timesheet = frappe.get_doc("User Timesheet", ts_name)
		timesheet.ut_status = ts_status
		timesheet.save()

	return {"ok": True, "updated": updated}
