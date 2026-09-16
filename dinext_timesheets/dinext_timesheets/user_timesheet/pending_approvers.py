"""Pending UT approver names for the form banner (ISS-2026-00926)."""

from __future__ import annotations

import json

import frappe

from .permissions import assert_can_read_timesheet

PENDING_STATUS = "На согласовании"
UTP_DOCTYPE = "User Timesheet Position"


def list_pending_approver_names(ts_name: str) -> list[str]:
	"""Full names of waiting approvers. Same list for author and approver."""
	assert_can_read_timesheet(ts_name)
	row = frappe.db.get_value(
		"User Timesheet",
		ts_name,
		["ut_status", "timesheet_from"],
		as_dict=True,
	)
	if not row or row.get("ut_status") != PENDING_STATUS:
		return []

	positions = frappe.get_all(
		UTP_DOCTYPE,
		filters={"user_timesheet": ts_name},
		pluck="name",
		ignore_permissions=True,
	)
	if not positions:
		return []

	owner = row.get("timesheet_from") or ""
	wf_tasks = frappe.get_all(
		"Workflow Task",
		filters={
			"status": "Working",
			"state": PENDING_STATUS,
			"doc": UTP_DOCTYPE,
			"wt_docname": ["in", positions],
			"_assign": ["not like", f"%{owner}%"] if owner else ["!=", ""],
		},
		fields=["_assign"],
		ignore_permissions=True,
	)

	emails: list[str] = []
	seen: set[str] = set()
	for task in wf_tasks:
		for user in _assign_users(task.get("_assign")):
			if not user or user == owner or user in seen:
				continue
			seen.add(user)
			emails.append(user)
	if not emails:
		return []

	users = frappe.get_all(
		"User",
		filters={"name": ["in", emails]},
		fields=["name", "full_name"],
		ignore_permissions=True,
	)
	by_name = {u["name"]: (u.get("full_name") or u["name"]) for u in users}
	return [by_name[email] for email in emails if email in by_name]


def _assign_users(raw) -> list[str]:
	if not raw:
		return []
	parsed = raw
	if isinstance(raw, str):
		try:
			parsed = json.loads(raw)
		except ValueError:
			return []
	if not isinstance(parsed, list):
		return []
	return [str(item) for item in parsed if item]
