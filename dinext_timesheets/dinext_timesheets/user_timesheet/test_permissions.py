# Copyright (c) 2026, Dinext and contributors
"""Unit tests for UT reprocess JE permission (ISS-2026-00926)."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from dinext_timesheets.dinext_timesheets.user_timesheet.permissions import (
	assert_can_reprocess_journal_entries,
	can_reprocess_journal_entries,
)


class TestReprocessJournalEntriesPerm(unittest.TestCase):
	@patch(
		"dinext_timesheets.dinext_timesheets.user_timesheet.permissions.frappe.has_permission",
		return_value=True,
	)
	def test_import_perm_allows(self, _has_perm):
		self.assertTrue(can_reprocess_journal_entries("director@example.com"))

	@patch(
		"dinext_timesheets.dinext_timesheets.user_timesheet.permissions.frappe.has_permission",
		return_value=False,
	)
	def test_no_import_perm_denies(self, _has_perm):
		self.assertFalse(can_reprocess_journal_entries("worker@example.com"))

	@patch(
		"dinext_timesheets.dinext_timesheets.user_timesheet.permissions.frappe.throw",
		side_effect=PermissionError("denied"),
	)
	@patch(
		"dinext_timesheets.dinext_timesheets.user_timesheet.permissions.frappe.has_permission",
		return_value=False,
	)
	def test_assert_throws_without_perm(self, _has_perm, throw):
		with self.assertRaises(PermissionError):
			assert_can_reprocess_journal_entries("worker@example.com")
		throw.assert_called_once()
