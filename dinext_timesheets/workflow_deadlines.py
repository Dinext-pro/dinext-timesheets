"""Timesheet-owned approver groups for the approval deadline report."""

from collections.abc import Mapping

import frappe


def approver_groups(approvers: tuple[str, ...]) -> Mapping[str, str]:
	if not approvers or not frappe.db.exists("DocType", "Worker") or not frappe.has_permission("Worker", "read"):
		return {}

	workers = frappe.get_list(
		"Worker",
		filters={"wuser": ["in", approvers]},
		fields=["wuser", "wuser_group"],
		limit_page_length=0,
	)
	return {
		worker["wuser"]: worker["wuser_group"]
		for worker in workers
		if worker.get("wuser") and worker.get("wuser_group")
	}
