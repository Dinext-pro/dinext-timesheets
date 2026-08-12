"""Install helpers for dinext_timesheets."""

from __future__ import annotations

import frappe

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
