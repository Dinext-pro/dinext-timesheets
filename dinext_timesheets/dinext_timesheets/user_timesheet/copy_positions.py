"""Copy UTP candidates from previous UT / PWA (demodev SS port)."""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import add_days, getdate

from .permissions import assert_can_write_timesheet
from .tasks import load_projects_remap2_customers


def build_response(success, message="", positions=None, duplicates=None, invalid=None):
	positions = positions or []
	duplicates = duplicates or []
	invalid = invalid or []
	return {
		"success": success,
		"message": message,
		"data": {
			"positions": positions,
			"copied_count": len(positions),
			"duplicates_count": len(duplicates),
			"invalid_count": len(invalid),
			"duplicate_items": duplicates,
			"invalid_items": invalid,
		},
	}


def _parse_doc_name(doc_data):
	if not doc_data:
		return None
	if isinstance(doc_data, str):
		try:
			doc_data = json.loads(doc_data)
		except Exception:
			name_start = doc_data.find('"name":"') + 8
			name_end = doc_data.find('"', name_start)
			if name_start > 7 and name_end > name_start:
				return doc_data[name_start:name_end]
			return None
	if isinstance(doc_data, dict):
		return doc_data.get("name")
	return getattr(doc_data, "name", None)


def get_current_timesheet_name(doc=None):
	doc_data = doc if doc is not None else frappe.form_dict.get("doc")
	return _parse_doc_name(doc_data)


def _valid_task_ids_from_tree(tree):
	valid = set()
	for customer in tree or []:
		for projects in customer.values():
			for project in projects or []:
				for item in project.get("tasks_issues") or []:
					if item.get("tsdoctype") == "Task" and item.get("name"):
						valid.add(item["name"])
	return valid


def get_valid_tasks_for_timesheet(timesheet):
	template_name = (
		frappe.db.get_value("Worker", {"wuser": timesheet.timesheet_from}, "wtimesheet_template")
		or timesheet.ts_from_template
	)
	if not template_name:
		return set()
	tree = load_projects_remap2_customers(
		template_name,
		timesheet.ts_valid_from,
		timesheet.ts_valid_for,
		timesheet.timesheet_from,
	)
	return _valid_task_ids_from_tree(tree)


def get_valid_tasks_from_request(valid_tasks=None):
	data = valid_tasks if valid_tasks is not None else frappe.form_dict.get("valid_tasks")
	if not data:
		return set()
	if isinstance(data, str):
		try:
			data = json.loads(data)
		except Exception:
			return set()
	if isinstance(data, list):
		return set(data)
	return set()


def _position_signature(row):
	return (
		row.get("document_type"),
		row.get("document_name"),
		row.get("user"),
		row.get("project"),
		row.get("project_role"),
	)


def copy_from_previous_timesheet(doc=None):
	name = get_current_timesheet_name(doc)
	if not name:
		return build_response(False, _("Could not determine timesheet name"))

	assert_can_write_timesheet(name)
	current = frappe.get_doc("User Timesheet", name)
	valid_from = getdate(current.ts_valid_from)
	previous_day = add_days(valid_from, -1)
	previous = frappe.get_all(
		"User Timesheet",
		filters={"timesheet_from": current.timesheet_from, "ts_valid_for": previous_day},
		fields=["name"],
		limit=1,
	)
	if not previous:
		return build_response(True, _("No timesheet found for the previous day"))

	previous_name = previous[0].name
	previous_positions = frappe.get_all(
		"User Timesheet Position",
		filters={"user_timesheet": previous_name},
		fields=["owner", "document_type", "document_name", "user", "project", "project_role"],
	)
	if not previous_positions:
		return build_response(True, _("The previous timesheet has no positions to copy"))

	existing = frappe.get_all(
		"User Timesheet Position",
		filters={"user_timesheet": name},
		fields=["document_type", "document_name", "user", "project", "project_role"],
	)
	existing_sigs = {_position_signature(ep) for ep in existing}
	valid_tasks = get_valid_tasks_for_timesheet(current)

	positions_to_copy = []
	duplicates = []
	invalid = []
	for position in previous_positions:
		if position.get("document_type") != "Task":
			continue
		task_name = position.get("document_name")
		sig = _position_signature(position)
		if sig in existing_sigs:
			duplicates.append(task_name)
			continue
		if task_name not in valid_tasks:
			invalid.append(task_name)
			continue
		positions_to_copy.append(
			{
				"document_type": position.get("document_type"),
				"document_name": task_name,
				"project": position.get("project"),
				"project_role": position.get("project_role"),
				"user": position.get("user"),
				"owner": position.get("owner"),
			}
		)
		existing_sigs.add(sig)

	return build_response(
		True,
		positions=positions_to_copy,
		duplicates=duplicates,
		invalid=invalid,
	)


def intersects_timesheet_period(assignment, timesheet_start, timesheet_end):
	assignment_start = assignment.get("date_from")
	assignment_end = assignment.get("date_to")
	if assignment_start:
		assignment_start = getdate(assignment_start)
	if assignment_end:
		assignment_end = getdate(assignment_end)
	if assignment_start and assignment_end:
		return assignment_start <= timesheet_end and assignment_end >= timesheet_start
	if assignment_start:
		return assignment_start <= timesheet_end
	if assignment_end:
		return assignment_end >= timesheet_start
	return True


def copy_from_project_workload_assignment(doc=None, valid_tasks=None):
	name = get_current_timesheet_name(doc)
	if not name:
		return build_response(False, _("Could not determine timesheet name"))

	assert_can_write_timesheet(name)
	current = frappe.get_doc("User Timesheet", name)
	valid_from = getdate(current.ts_valid_from)
	valid_for = getdate(current.ts_valid_for)
	valid_task_ids = get_valid_tasks_from_request(valid_tasks)

	assignments = frappe.get_all(
		"Project Workload Assignment",
		filters={"user": current.timesheet_from},
		fields=["name", "owner", "task", "role", "user", "date_from", "date_to"],
	)
	relevant = [
		a for a in assignments if intersects_timesheet_period(a, valid_from, valid_for)
	]
	if not relevant:
		return build_response(
			True, _("No planned workload data found for the current timesheet period")
		)

	task_names = []
	seen = set()
	for assignment in relevant:
		task_name = assignment.get("task")
		if task_name and task_name not in seen:
			seen.add(task_name)
			task_names.append(task_name)

	task_projects = {}
	if task_names:
		for row in frappe.get_all(
			"Task", filters={"name": ["in", task_names]}, fields=["name", "project"]
		):
			task_projects[row.name] = row.project

	existing = frappe.get_all(
		"User Timesheet Position",
		filters={"user_timesheet": name},
		fields=["document_type", "document_name", "user", "project", "project_role"],
	)
	existing_sigs = {_position_signature(ep) for ep in existing}

	positions_to_copy = []
	duplicates = []
	invalid = []
	for assignment in relevant:
		task_name = assignment.get("task")
		project_name = task_projects.get(task_name)
		project_role = assignment.get("role")
		assignment_user = assignment.get("user")
		if not task_name or not project_name:
			invalid.append(task_name or assignment.get("name"))
			continue
		sig = ("Task", task_name, assignment_user, project_name, project_role)
		if sig in existing_sigs:
			duplicates.append(task_name)
			continue
		if task_name not in valid_task_ids:
			invalid.append(task_name)
			continue
		positions_to_copy.append(
			{
				"document_type": "Task",
				"document_name": task_name,
				"project": project_name,
				"project_role": project_role,
				"user": assignment_user,
				"owner": assignment.get("owner"),
			}
		)
		existing_sigs.add(sig)

	return build_response(
		True,
		_("Planned workload positions processed"),
		positions=positions_to_copy,
		duplicates=duplicates,
		invalid=invalid,
	)
