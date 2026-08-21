"""Whitelist facades for User Timesheet (ISS-2026-00926 try3).

Port from demodev Server Scripts — see try3/timesheet/inventory-demodev.md.
Limits: call project_workload_assignment.api.calculate_user_timesheet_limits (do not duplicate).
"""

from __future__ import annotations

import frappe

from .copy_positions import (
	copy_from_previous_timesheet,
	copy_from_project_workload_assignment,
)
from .permissions import assert_can_query_tasks_for_owner
from .status import set_timesheet_status as _set_timesheet_status
from .tasks import load_projects_remap2_customers


def _form_arg(name: str, explicit=None):
	if explicit is not None and explicit != "":
		return explicit
	return frappe.form_dict.get(name)


@frappe.whitelist()
def get_timesheet_tasks(template_name=None, ts_start=None, ts_end=None, ts_owner=None):
	"""Return customer→projects→tasks/issues tree for UT task picker."""
	owner = _form_arg("ts_owner", ts_owner)
	assert_can_query_tasks_for_owner(owner)
	return load_projects_remap2_customers(
		_form_arg("template_name", template_name),
		_form_arg("ts_start", ts_start),
		_form_arg("ts_end", ts_end),
		owner,
	)


@frappe.whitelist()
def copy_positions_from_previous_timesheet(doc=None):
	"""Candidates to copy from previous period UT."""
	return copy_from_previous_timesheet(_form_arg("doc", doc))


@frappe.whitelist()
def copy_positions_from_project_workload_assignment(doc=None, valid_tasks=None):
	"""Candidates to copy from Project Workload Assignment."""
	return copy_from_project_workload_assignment(
		_form_arg("doc", doc),
		_form_arg("valid_tasks", valid_tasks),
	)


@frappe.whitelist()
def set_timesheet_status(positions=None, pos_status=None, ts_name=None, ts_status=None):
	"""Update UTP (+ optional UT) status / workflow_state."""
	return _set_timesheet_status(
		positions=_form_arg("positions", positions),
		pos_status=_form_arg("pos_status", pos_status),
		ts_name=_form_arg("ts_name", ts_name),
		ts_status=_form_arg("ts_status", ts_status),
	)
