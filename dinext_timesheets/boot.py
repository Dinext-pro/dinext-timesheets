# Copyright (c) 2026, Dinext and contributors
"""Desk bootinfo for timesheet limits UI flags."""

from __future__ import annotations

import frappe

from dinext_timesheets.dinext_timesheets.user_timesheet.status import has_legacy_position_status

HOOK = "dinext_timesheet_show_forecast"


def extend_bootinfo(bootinfo) -> None:
	"""Expose opt-in Forecast column flag. Default off unless a tenant hook is on."""
	values = frappe.get_hooks(HOOK) or []
	bootinfo.dinext_timesheet_show_forecast = any(bool(v) for v in values)
	bootinfo.dinext_timesheet_legacy_position_status = has_legacy_position_status()
