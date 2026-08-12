# Copyright (c) 2026, Dinext and contributors
# For license information, please see license.txt

"""Register this app's default Dinext Hub cards."""

from __future__ import annotations

import frappe

APP_NAME = 'dinext_timesheets'

HUB_ITEMS = (
	{
		"section": 'My Work',
		"element_type": 'Workspace',
		"target": 'Мои Таймшиты',
		"label": 'My Timesheets',
		"description": 'Personal time-tracking hub: your timesheets, leave and expense requests, pending approvals, utilization reports, and related settings.',
		"icon": 'hr',
	},
)


def register_dinext_hub_items() -> None:
	if "dinext_common" not in frappe.get_installed_apps():
		return

	try:
		from dinext_common.setup.hub_catalog import register_hub_items
	except ImportError:
		return

	register_hub_items(HUB_ITEMS, source_app=APP_NAME)
