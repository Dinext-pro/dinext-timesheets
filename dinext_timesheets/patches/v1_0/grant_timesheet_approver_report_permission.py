"""Grant approvers access to reports on User Timesheet."""

import frappe
from frappe.permissions import add_permission, update_permission_property


def execute():
	doctype = "User Timesheet"
	role = "Dinext_UTP_Appoval"
	permission = frappe.db.get_value(
		"Custom DocPerm",
		{"parent": doctype, "role": role, "permlevel": 0, "if_owner": 0},
		["name", "report"],
		as_dict=True,
	)
	if not permission:
		new_rule = add_permission(doctype, role, permlevel=0, ptype="read")
		if new_rule:
			frappe.db.set_value("Custom DocPerm", new_rule, "export", 0, update_modified=False)
	if not permission or not permission.report:
		update_permission_property(doctype, role, permlevel=0, ptype="report", value=1)
