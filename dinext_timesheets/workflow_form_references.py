"""Workflow approval references for a Timesheet form."""

import frappe


def timesheet_positions(source) -> tuple[str, list[str]]:
	doctype = "User Timesheet Position"
	return doctype, frappe.get_all(doctype, filters={"user_timesheet": source.name}, pluck="name")
