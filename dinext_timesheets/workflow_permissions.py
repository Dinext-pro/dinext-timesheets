"""Preserve Workflow Task read access alongside Timesheets role overrides."""

import frappe


def restore_workflow_task_base_read(*, during_cutover: bool = False) -> None:
	"""Keep standard document and report access with Timesheets role overrides."""
	if not during_cutover and not frappe.conf.get("enable_parallel_workflow_approval"):
		return
	from dinext_common.workflow_approval.permissions import supports_final_task_permission_queries

	if not supports_final_task_permission_queries():
		return
	doctype = "Workflow Task"
	timesheet_roles = ("Dinext_User", "Dinext_UTP_Appoval", "Dinext_UT_Full_Access")
	if not frappe.db.exists("Custom DocPerm", {"parent": doctype, "role": ("in", timesheet_roles)}):
		return
	base = {"parent": doctype, "role": "All", "permlevel": 0, "if_owner": 0}
	existing = frappe.db.get_value("Custom DocPerm", base, ["name", "read", "report"], as_dict=True)
	if existing:
		if not existing.read or existing.report:
			return
		frappe.db.set_value("Custom DocPerm", existing.name, {"report": 1})
	else:
		frappe.get_doc({
			"doctype": "Custom DocPerm", "parenttype": "DocType", "parentfield": "permissions",
			**base, "read": 1, "report": 1,
		}).insert(ignore_permissions=True)
	frappe.clear_cache(doctype=doctype)
