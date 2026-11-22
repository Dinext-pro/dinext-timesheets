"""Workflow approval references for a Timesheet form."""

import frappe


def timesheet_positions(source) -> tuple[str, list[str]]:
	from dinext_common.workflow_approval.permissions import prepare_source_permissions

	doctype = "User Timesheet Position"
	names = frappe.get_all(doctype, filters={"user_timesheet": source.name}, pluck="name")
	permissions = {}
	prepare_source_permissions(
		[{"reference_doctype": doctype, "reference_name": name} for name in names],
		frappe.session.user,
		permissions,
	)
	return doctype, [
		name for name in names
		if (permissions[(doctype, name)] if (doctype, name) in permissions
			else frappe.has_permission(doctype, "read", doc=name))
	]
