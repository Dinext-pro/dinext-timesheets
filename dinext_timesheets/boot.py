# Copyright (c) 2026, Dinext and contributors
"""Desk bootinfo for timesheet limits UI flags."""

from __future__ import annotations

import frappe

from dinext_timesheets.dinext_timesheets.user_timesheet.status import has_legacy_position_status

HOOK = "dinext_timesheet_show_forecast"


def extend_bootinfo(bootinfo) -> None:
	"""Expose Timesheets settings needed by Desk."""
	values = frappe.get_hooks(HOOK) or []
	bootinfo.dinext_timesheet_show_forecast = any(bool(v) for v in values)
	bootinfo.dinext_timesheet_legacy_position_status = has_legacy_position_status()
	bootinfo.setdefault("dinext_workflow_custom_form_banners", []).append("User Timesheet")
