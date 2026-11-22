# Copyright (c) 2026, Dinext and contributors
"""Unit tests for timesheet forecast boot flag."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import frappe

from dinext_timesheets.boot import extend_bootinfo


class TestBootForecastFlag(unittest.TestCase):
	def setUp(self):
		self.enterContext(patch("dinext_timesheets.boot.has_legacy_position_status", return_value=False))

	@patch("dinext_timesheets.boot.frappe.get_hooks", return_value=[])
	def test_default_off(self, _hooks):
		boot = frappe._dict()
		extend_bootinfo(boot)
		self.assertFalse(boot.dinext_timesheet_show_forecast)

	@patch("dinext_timesheets.boot.frappe.get_hooks", return_value=[0, None, ""])
	def test_falsy_hook_off(self, _hooks):
		boot = frappe._dict()
		extend_bootinfo(boot)
		self.assertFalse(boot.dinext_timesheet_show_forecast)

	@patch("dinext_timesheets.boot.frappe.get_hooks", return_value=[1])
	def test_tenant_hook_on(self, _hooks):
		boot = frappe._dict()
		extend_bootinfo(boot)
		self.assertTrue(boot.dinext_timesheet_show_forecast)
