"""Convert exclusion settings once, without changing workflow or position data."""

import frappe
from dinext_timesheets.timesheet_settings import (
	position_workflow_states,
	seed_default_rules,
)
from dinext_timesheets.timesheet_status import POSITION_PENDING, POSITION_STATUS_UNSET
from frappe.utils import cint


def execute():
	if not frappe.db.exists("Timesheet Settings", "Timesheet Settings"):
		seed_default_rules()
		return
	doc = frappe.get_single("Timesheet Settings")
	if cint(doc.get("position_list_visibility_migrated")):
		return
	# Respect any already supplied explicit configuration.
	if not doc.get("visible_list_statuses"):
		hidden = {row.position_status for row in doc.get("hidden_list_statuses", [])}
		states = list(dict.fromkeys([*position_workflow_states(), POSITION_STATUS_UNSET]))
		for state in states:
			if state not in hidden:
				doc.append(
					"visible_list_statuses",
					{"position_status": state, "open_wf_task": int(state == POSITION_PENDING)},
				)
		for row in doc.get("visible_list_statuses", []):
			row.db_insert()
	# Avoid unrelated rollup validation/hooks on historical settings during migration.
	frappe.db.set_single_value("Timesheet Settings", "position_list_visibility_migrated", 1)
	frappe.clear_document_cache("Timesheet Settings", "Timesheet Settings")
