"""Remove the obsolete Workflow Transition field after checking route parity."""

import frappe
from frappe import _
from frappe.utils import cint

from dinext_timesheets.dinext_timesheets.user_timesheet.permissions import (
	is_timesheet_management_transition,
)

FIELDNAME = "custom_timesheet_management_action"
FIELD = f"Workflow Transition-{FIELDNAME}"


def execute():
	if not frappe.db.exists("Custom Field", FIELD):
		return

	timesheet_workflows = set(frappe.get_all(
		"Workflow", filters={"document_type": "User Timesheet Position"}, pluck="name",
	))
	transitions = frappe.get_all(
		"Workflow Transition",
		fields=["parent", "name", "state", "action", "next_state", "allow_self_approval", FIELDNAME],
		order_by="parent, idx",
	)
	mismatches = []
	for row in transitions:
		was_direct = bool(cint(row.get(FIELDNAME)))
		is_direct = row.parent in timesheet_workflows and is_timesheet_management_transition(row)
		if was_direct != is_direct:
			mismatches.append(f"{row.parent} / {row.name}: {row.state} → {row.action} → {row.next_state}")
	if mismatches:
		frappe.throw(
			_("Cannot remove the Timesheet Management Action field. These transitions need review: {0}").format(
				"; ".join(mismatches)
			),
		)

	frappe.delete_doc("Custom Field", FIELD, ignore_permissions=True)
