# Copyright (c) 2026, Dinext and contributors
"""Unit tests for UT pending-approver banner list."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from dinext_timesheets.dinext_timesheets.user_timesheet.pending_approvers import (
	list_pending_approver_names,
)


class TestListPendingApproverNames(unittest.TestCase):
	@patch(
		"dinext_timesheets.dinext_timesheets.user_timesheet.pending_approvers.frappe.get_all"
	)
	@patch(
		"dinext_timesheets.dinext_timesheets.user_timesheet.pending_approvers.frappe.db.get_value",
		return_value={"ut_status": "На согласовании", "timesheet_from": "administrator@dinext.invalid"},
	)
	@patch(
		"dinext_timesheets.dinext_timesheets.user_timesheet.permissions.frappe.has_permission",
		return_value=True,
	)
	@patch(
		"dinext_timesheets.dinext_timesheets.user_timesheet.permissions.frappe.get_doc",
		return_value=object(),
	)
	@patch(
		"dinext_timesheets.dinext_timesheets.user_timesheet.permissions.frappe.db.exists",
		return_value=True,
	)
	def test_approver_sees_all_waiting_names(
		self, _exists, _get_doc, _has_perm, _get_value, get_all
	):
		get_all.side_effect = [
			["UTP-1", "UTP-2"],
			[
				{"_assign": '["administrator@dinext.invalid"]'},
				{"_assign": '["administrator@dinext.invalid", "administrator@dinext.invalid"]'},
			],
			[
				{"name": "administrator@dinext.invalid", "full_name": "Administrator"},
				{"name": "administrator@dinext.invalid", "full_name": "Administrator"},
			],
		]
		self.assertEqual(
			list_pending_approver_names("TS-1"),
			["Иван Лидов", "Пётр Пмов"],
		)

	@patch(
		"dinext_timesheets.dinext_timesheets.user_timesheet.permissions.frappe.throw",
		side_effect=PermissionError("denied"),
	)
	@patch(
		"dinext_timesheets.dinext_timesheets.user_timesheet.permissions.frappe.has_permission",
		return_value=False,
	)
	@patch(
		"dinext_timesheets.dinext_timesheets.user_timesheet.permissions.frappe.get_doc",
		return_value=object(),
	)
	@patch(
		"dinext_timesheets.dinext_timesheets.user_timesheet.permissions.frappe.db.exists",
		return_value=True,
	)
	def test_no_read_throws(self, _exists, _get_doc, _has_perm, throw):
		with self.assertRaises(PermissionError):
			list_pending_approver_names("TS-SECRET")
		throw.assert_called_once()

	@patch(
		"dinext_timesheets.dinext_timesheets.user_timesheet.pending_approvers.frappe.get_all"
	)
	@patch(
		"dinext_timesheets.dinext_timesheets.user_timesheet.pending_approvers.frappe.db.get_value",
		return_value={"ut_status": "Черновик", "timesheet_from": "administrator@dinext.invalid"},
	)
	@patch(
		"dinext_timesheets.dinext_timesheets.user_timesheet.permissions.frappe.has_permission",
		return_value=True,
	)
	@patch(
		"dinext_timesheets.dinext_timesheets.user_timesheet.permissions.frappe.get_doc",
		return_value=object(),
	)
	@patch(
		"dinext_timesheets.dinext_timesheets.user_timesheet.permissions.frappe.db.exists",
		return_value=True,
	)
	def test_draft_returns_empty(
		self, _exists, _get_doc, _has_perm, _get_value, get_all
	):
		self.assertEqual(list_pending_approver_names("TS-DRAFT"), [])
		get_all.assert_not_called()
