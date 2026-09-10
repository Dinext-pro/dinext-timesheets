# Copyright (c) 2026, Dinext and contributors
# For license information, please see license.txt

"""Install / migrate hooks for Dinext Timesheets."""

from __future__ import annotations

import frappe

from dinext_timesheets.setup.dinext_hub import register_dinext_hub_items

OWNED_PROJECT_TEAM_FIELDS = (
	"pt_worker",
	"allow_approval",
)


def detach_owned_project_team_fields() -> None:
	"""Detach DocFields re-owned as Custom Fields before fixture sync.

	CI still pins dinext_projects releases that define these as DocFields.
	`after_install` runs before sync_fixtures, so delete_fields makes install idempotent.
	"""
	from frappe.model import delete_fields

	delete_fields({"Project Team Details": list(OWNED_PROJECT_TEAM_FIELDS)}, delete=0)
	frappe.clear_cache(doctype="Project Team Details")


def after_install() -> None:
	detach_owned_project_team_fields()
	register_dinext_hub_items()


def after_migrate() -> None:
	from dinext_timesheets.dinext_timesheets.user_timesheet._disable_cutover_scripts import (
		run as disable_cutover_scripts,
	)

	register_dinext_hub_items()
	# Fixtures still ship enabled=1 CS/SS; without this, migrate re-enables
	# V10 / UT_Accept_WF / Set Timesheet Status and form RPC goes bare again.
	disable_cutover_scripts()
	from dinext_timesheets.patches.v1_0.configure_parallel_workflows_v2 import (
		execute as configure_parallel_workflows,
	)

	configure_parallel_workflows()
