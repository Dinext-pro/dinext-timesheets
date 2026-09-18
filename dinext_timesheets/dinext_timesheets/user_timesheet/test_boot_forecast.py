# Copyright (c) 2026, Dinext and contributors
"""Unit tests for timesheet forecast boot flag."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from dinext_timesheets.boot import extend_bootinfo


class TestBootForecastFlag(unittest.TestCase):
	@patch("dinext_timesheets.boot.frappe.get_hooks", return_value=[])
	def test_default_off(self, _hooks):
		boot = SimpleNamespace()
		extend_bootinfo(boot)
		self.assertFalse(boot.dinext_timesheet_show_forecast)

	@patch("dinext_timesheets.boot.frappe.get_hooks", return_value=[0, None, ""])
	def test_falsy_hook_off(self, _hooks):
		boot = SimpleNamespace()
		extend_bootinfo(boot)
		self.assertFalse(boot.dinext_timesheet_show_forecast)

	@patch("dinext_timesheets.boot.frappe.get_hooks", return_value=[1])
	def test_tenant_hook_on(self, _hooks):
		boot = SimpleNamespace()
		extend_bootinfo(boot)
		self.assertTrue(boot.dinext_timesheet_show_forecast)
