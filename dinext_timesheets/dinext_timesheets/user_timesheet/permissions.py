"""Server-side authorization for User Timesheet whitelist API."""

from __future__ import annotations

import frappe
from frappe import _


def _is_system_manager() -> bool:
	user = frappe.session.user
	if user == "Administrator":
		return True
	if user in (None, "", "Guest"):
		return False
	return "System Manager" in frappe.get_roles(user)


def assert_can_query_tasks_for_owner(ts_owner: str) -> None:
	"""Caller may load task tree for ts_owner (self, SM, or read access to their UT)."""
	if not ts_owner:
		frappe.throw(_("Missing ts_owner"), frappe.PermissionError)

	user = frappe.session.user
	if user == ts_owner or _is_system_manager():
		return

	names = frappe.get_all(
		"User Timesheet",
		filters={"timesheet_from": ts_owner},
		pluck="name",
		limit_page_length=20,
	)
	for name in names:
		if frappe.has_permission("User Timesheet", "read", doc=name):
			return

	frappe.throw(
		_("Not permitted to load timesheet tasks for user {0}").format(ts_owner),
		frappe.PermissionError,
	)


def assert_can_set_timesheet_status(items, ts_name=None, ts_status=None) -> None:
	"""Caller may write listed UTP and optional parent UT; UTP must belong to ts_name if set."""
	for p in items or []:
		name = p if isinstance(p, str) else (p or {}).get("name")
		if not name:
			continue
		if not frappe.db.exists("User Timesheet Position", name):
			frappe.throw(_("User Timesheet Position {0} not found").format(name))

		position = frappe.get_doc("User Timesheet Position", name)
		if not frappe.has_permission("User Timesheet Position", "write", doc=position):
			frappe.throw(
				_("Not permitted to update {0}").format(name),
				frappe.PermissionError,
			)
		if ts_name and position.user_timesheet and position.user_timesheet != ts_name:
			frappe.throw(
				_("Position {0} does not belong to timesheet {1}").format(
					name, ts_name
				),
				frappe.ValidationError,
			)

	if ts_name and ts_status:
		assert_can_write_timesheet(ts_name)


def assert_can_write_timesheet(ts_name: str) -> None:
	"""Caller may write User Timesheet (copy / status)."""
	if not ts_name:
		frappe.throw(_("Timesheet name is required"), frappe.ValidationError)
	if not frappe.db.exists("User Timesheet", ts_name):
		frappe.throw(_("User Timesheet {0} not found").format(ts_name))
	timesheet = frappe.get_doc("User Timesheet", ts_name)
	if not frappe.has_permission("User Timesheet", "write", doc=timesheet):
		frappe.throw(
			_("Not permitted to update timesheet {0}").format(ts_name),
			frappe.PermissionError,
		)
