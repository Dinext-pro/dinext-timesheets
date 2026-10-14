"""Timesheet aggregate behavior for generic Workflow Task approvals."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import timedelta
from typing import Literal, TypedDict

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, nowdate

from dinext_timesheets.timesheet_status import (
	PARENT_APPROVED,
	PARENT_DRAFT as DRAFT,
	PARENT_PENDING as PENDING,
	PARENT_REJECTED as REJECTED,
	PARENT_REWORK as REWORK,
	POSITION_APPROVED,
	POSITION_EDITING as EDITING,
)

TimesheetOperation = Literal["Start", "Stop", "Edit"]


class TimesheetPositionDetailInput(TypedDict, total=False):
	date: str
	hours: float
	description: str


class TimesheetPositionInput(TypedDict, total=False):
	name: str
	project: str
	document_type: str
	document_name: str
	project_role: str
	table: list[TimesheetPositionDetailInput]
	details: list[TimesheetPositionDetailInput]


class TimesheetOrchestrationResponse(TypedDict):
	timesheet: str
	status: str
	processed: int
	positions: list[str]


def _enabled() -> bool:
	from dinext_common.workflow_approval.lifecycle import is_engine_enabled

	return is_engine_enabled()


def _value(row: object, fieldname: str, default=None):
	if isinstance(row, dict):
		return row.get(fieldname, default)
	return getattr(row, fieldname, default)


def _operation_states(
	operation: TimesheetOperation,
	*,
	has_positions: bool,
) -> tuple[str, str | None]:
	if operation not in {"Start", "Stop", "Edit"}:
		raise frappe.ValidationError(_("Unknown timesheet operation"))
	if not has_positions:
		return (REWORK, None) if operation == "Edit" else (PARENT_APPROVED, None)
	if operation == "Start":
		return PENDING, PENDING
	return REWORK, EDITING


def _current_team_lead(user_group: str | None, target_date: object) -> str | None:
	if not user_group or not target_date:
		return None
	return frappe.db.get_value(
		"Teamleads Table",
		{
			"parent": user_group,
			"date": ("<=", getdate(target_date)),
		},
		"teamlead",
		order_by="date desc, idx desc",
	)


def _authorize_operation(
	parent: object,
	operation: TimesheetOperation,
	*,
	actor: str | None = None,
) -> None:
	if operation not in {"Start", "Stop", "Edit"}:
		raise frappe.ValidationError(_("Unknown timesheet operation"))
	actor = actor or frappe.session.user
	owner = str(_value(parent, "timesheet_from") or "")
	status = str(_value(parent, "ut_status") or "")
	if operation == "Stop":
		if actor != owner:
			raise frappe.PermissionError(_("Only the timesheet owner can stop approval"))
		if status != PENDING:
			raise frappe.ValidationError(_("Only a pending timesheet can be stopped"))
		return
	allowed_statuses = {
		"Start": {DRAFT, REWORK},
		"Edit": {PARENT_APPROVED, REJECTED},
	}
	if status not in allowed_statuses[operation]:
		raise frappe.ValidationError(
			_("Operation {0} is not available for timesheet status {1}").format(
				operation,
				status,
			)
		)
	if actor == owner or "System Manager" in frappe.get_roles(actor):
		return
	if (
		"Dinext_Team_Lead" in frappe.get_roles(actor)
		and _current_team_lead(
			_value(parent, "user_group"),
			_value(parent, "ts_valid_from"),
		)
		== actor
	):
		return
	raise frappe.PermissionError(_("You are not allowed to manage this timesheet"))


def _domain_transition_actor(actor: str) -> str | None:
	"""Let Workflow choose an eligible actor for an authorized manager override."""
	return None if "System Manager" in frappe.get_roles(actor) else actor


def _parse_positions(positions: object) -> list[TimesheetPositionInput]:
	rows = frappe.parse_json(positions) if isinstance(positions, str) else positions
	if rows is None:
		return []
	if not isinstance(rows, list):
		raise frappe.ValidationError(_("Timesheet positions must be a list"))
	parsed: list[TimesheetPositionInput] = []
	for row in rows:
		if not isinstance(row, dict):
			raise frappe.ValidationError(_("Each timesheet position must be an object"))
		parsed.append(row)
	return parsed


def _parse_names(values: object) -> list[str]:
	rows = frappe.parse_json(values) if isinstance(values, str) else values
	if rows is None:
		return []
	if not isinstance(rows, list):
		raise frappe.ValidationError(_("Deleted positions must be a list"))
	return list(dict.fromkeys(str(row) for row in rows if row not in (None, "")))


def _position_label(position: object) -> str:
	return str(_value(position, "name") or _value(position, "document_name") or _("new position"))


def _validate_position_shape(
	parent: object,
	position: object,
	*,
	description_required: bool,
) -> list[str]:
	label = _position_label(position)
	errors: list[str] = []
	if not _value(position, "project"):
		errors.append(_("Position {0}: project is required").format(label))
	if _value(position, "document_type") not in {"Task", "Issue"}:
		errors.append(_("Position {0}: task or issue type is required").format(label))
	if not _value(position, "document_name"):
		errors.append(_("Position {0}: task or issue is required").format(label))
	if not _value(position, "project_role"):
		errors.append(_("Position {0}: project role is required").format(label))
	details = _value(position, "table") or _value(position, "details") or []
	total = 0.0
	seen_dates: set[object] = set()
	date_from = getdate(_value(parent, "ts_valid_from"))
	date_to = getdate(_value(parent, "ts_valid_for"))
	for detail in details:
		hours = flt(_value(detail, "hours"))
		date_value = _value(detail, "date")
		description = str(_value(detail, "description") or "").strip()
		if hours <= 0:
			errors.append(_("Position {0}: hours must be positive").format(label))
		if not date_value:
			errors.append(_("Position {0}: date is required").format(label))
			continue
		detail_date = getdate(date_value)
		if detail_date in seen_dates:
			errors.append(_("Position {0}: duplicate date {1}").format(label, detail_date))
		seen_dates.add(detail_date)
		if detail_date < date_from or detail_date > date_to:
			errors.append(
				_("Position {0}: date {1} is outside the timesheet period").format(
					label,
					detail_date,
				)
			)
		if description_required and hours > 0 and not description:
			errors.append(
				_("Position {0}: description is required for {1}").format(
					label,
					detail_date,
				)
			)
		total += hours
	if total <= 0:
		errors.append(_("Position {0}: total hours must be positive").format(label))
	return errors


def _dates_overlap(
	left_from: object,
	left_to: object,
	right_from: object,
	right_to: object,
) -> bool:
	return getdate(left_from) <= getdate(right_to) and getdate(right_from) <= getdate(left_to)


def _validate_parent_period(parent: object) -> list[str]:
	date_from = _value(parent, "ts_valid_from")
	date_to = _value(parent, "ts_valid_for")
	if not date_from or not date_to:
		return [_("Timesheet start and end dates are required")]
	if getdate(date_from) > getdate(date_to):
		return [_("Timesheet start date cannot be after its end date")]
	overlaps = frappe.get_all(
		"User Timesheet",
		filters={
			"timesheet_from": _value(parent, "timesheet_from"),
			"name": ("!=", _value(parent, "name")),
			"ts_valid_from": ("<=", getdate(date_to)),
			"ts_valid_for": (">=", getdate(date_from)),
		},
		pluck="name",
		limit=1,
	)
	if overlaps:
		return [_("Another timesheet overlaps this period")]
	return []


def _participant_values(user: str) -> set[str]:
	values = {
		user,
		*frappe.get_all(
			"Has Role",
			filters={"parenttype": "User", "parent": user},
			pluck="role",
		),
	}
	values.update(
		frappe.get_all(
			"User Group Member",
			filters={"user": user},
			pluck="parent",
		)
	)
	return {str(value) for value in values if value}


def _team_row_matches_period(row: object, parent: object, project: object) -> bool:
	row_from = _value(row, "pt_valid_from")
	row_to = _value(row, "pt_valid_for")
	if not row_from or not row_to:
		row_from = _value(project, "expected_start_date") or _value(parent, "ts_valid_from")
		row_to = _value(project, "expected_end_date") or _value(parent, "ts_valid_for")
	return _dates_overlap(
		row_from,
		row_to,
		_value(parent, "ts_valid_from"),
		_value(parent, "ts_valid_for"),
	)


def _validate_position_links(parent: object, position: object, template: object) -> list[str]:
	errors: list[str] = []
	label = _position_label(position)
	project_name = str(_value(position, "project") or "")
	document_type = str(_value(position, "document_type") or "")
	document_name = str(_value(position, "document_name") or "")
	role = str(_value(position, "project_role") or "")
	if not all((project_name, document_type, document_name, role)):
		return errors
	if document_type not in {"Task", "Issue"}:
		return errors
	project = frappe.db.get_value(
		"Project",
		project_name,
		["name", "status", "is_active", "expected_start_date", "expected_end_date"],
		as_dict=True,
	)
	if not project or project.status != "Open" or project.is_active != "Yes":
		errors.append(_("Position {0}: project is not active and open").format(label))
		return errors
	allowed_doctypes = {
		str(_value(row, "dtdoctype"))
		for row in (_value(template, "doctype_for_timesheet") or [])
		if _value(row, "dtdoctype")
	}
	if document_type not in allowed_doctypes:
		errors.append(
			_("Position {0}: document type is not enabled by the timesheet template").format(
				label
			)
		)
	if not frappe.db.exists("Project Role", role):
		errors.append(_("Position {0}: project role does not exist").format(label))
	source_fields = ["project", "custom_include"]
	if document_type == "Task":
		source_fields.extend(
			[
				"status",
				"is_milestone",
				"exp_start_date",
				"exp_end_date",
				"completed_on",
			]
		)
	source = frappe.db.get_value(
		document_type,
		document_name,
		source_fields,
		as_dict=True,
	)
	if not source or source.project != project_name:
		errors.append(
			_("Position {0}: task or issue does not belong to the selected project").format(
				label
			)
		)
	else:
		if not cint(source.custom_include):
			errors.append(
				_("Position {0}: task or issue is excluded from timesheets").format(label)
			)
		if document_type == "Task":
			if source.status in {"Cancelled", "Template"} or cint(source.is_milestone):
				errors.append(
					_("Position {0}: task is not eligible for timesheets").format(label)
				)
			date_from = getdate(_value(parent, "ts_valid_from"))
			date_to = getdate(_value(parent, "ts_valid_for"))
			start = getdate(source.exp_start_date) if source.exp_start_date else None
			end = (
				getdate(source.completed_on)
				if source.status == "Completed" and source.completed_on
				else getdate(source.exp_end_date)
				if source.exp_end_date
				else None
			)
			if not start or start > date_to or not end or end < date_from:
				errors.append(
					_("Position {0}: task is outside the timesheet period").format(label)
				)
		owner = str(_value(parent, "timesheet_from"))
		has_open_assignment = frappe.db.exists(
			"ToDo",
			{
				"allocated_to": owner,
				"status": "Open",
				"reference_type": document_type,
				"reference_name": document_name,
			},
		)
		has_read_share = frappe.db.exists(
			"DocShare",
			{
				"user": owner,
				"read": 1,
				"share_doctype": document_type,
				"share_name": document_name,
			},
		)
		if not (has_open_assignment or has_read_share):
			errors.append(
				_("Position {0}: task or issue is not assigned or shared with the owner").format(
					label
				)
			)
	team_rows = frappe.get_all(
		"Project Team Details",
		filters={
			"parent": project_name,
			"pt_role": role,
			"pt_participant": (
				"in",
				sorted(_participant_values(str(_value(parent, "timesheet_from")))),
			),
		},
		fields=["pt_valid_from", "pt_valid_for"],
	)
	if not any(_team_row_matches_period(row, parent, project) for row in team_rows):
		errors.append(
			_("Position {0}: project role is not valid for the owner and period").format(
				label
			)
		)
	return errors


def _calendar_context(parent: object) -> tuple[object, set[object], dict[object, float], dict[object, float]]:
	worker_name = frappe.db.get_value(
		"Worker",
		{"wuser": _value(parent, "timesheet_from")},
		"name",
	)
	if not worker_name:
		raise frappe.ValidationError(_("Timesheet owner has no Worker record"))
	worker = frappe.get_doc("Worker", worker_name)
	if not worker.wtimesheet_template:
		raise frappe.ValidationError(_("Worker has no Timesheet Template"))
	template = frappe.get_doc("Timesheet Template", worker.wtimesheet_template)
	date_from = getdate(_value(parent, "ts_valid_from"))
	date_to = getdate(_value(parent, "ts_valid_for"))
	if not worker.wholiday_list:
		raise frappe.ValidationError(_("Worker has no Holiday List"))
	holiday_list = frappe.db.get_value(
		"Holiday List",
		worker.wholiday_list,
		["from_date", "to_date"],
		as_dict=True,
	)
	if (
		not holiday_list
		or not holiday_list.from_date
		or not holiday_list.to_date
		or getdate(holiday_list.from_date) > date_from
		or getdate(holiday_list.to_date) < date_to
	):
		raise frappe.ValidationError(
			_("Holiday List is not active for the whole timesheet period")
		)
	holidays = {
		getdate(row.holiday_date)
		for row in frappe.get_all(
			"Holiday",
			filters={
				"parent": worker.wholiday_list,
				"holiday_date": ("between", [date_from, date_to]),
			},
			fields=["holiday_date"],
		)
	}
	reduced: dict[object, float] = {}
	if template.tt_working_hours_on_date:
		working_hours = frappe.db.get_value(
			"Working Hours On Date",
			template.tt_working_hours_on_date,
			["hod_from_date", "hod_to_date"],
			as_dict=True,
		)
		if (
			not working_hours
			or not working_hours.hod_from_date
			or not working_hours.hod_to_date
			or getdate(working_hours.hod_from_date) > date_from
			or getdate(working_hours.hod_to_date) < date_to
		):
			raise frappe.ValidationError(
				_("Working Hours On Date is not active for the whole timesheet period")
			)
		reduced = {
			getdate(row.wht_date): flt(row.wht_hours)
			for row in frappe.get_all(
				"Working Hours Table",
				filters={
					"parent": template.tt_working_hours_on_date,
					"wht_date": (
						"between",
						[
							date_from,
							date_to,
						],
					),
				},
				fields=["wht_date", "wht_hours"],
			)
		}
	leave_hours: dict[object, float] = defaultdict(float)
	leave_rows = frappe.get_all(
		"Application For Leave",
		filters={
			"lauser": _value(parent, "timesheet_from"),
			"status": POSITION_APPROVED,
			"alfrom_date": ("<=", getdate(_value(parent, "ts_valid_for"))),
			"alto_date": (">=", getdate(_value(parent, "ts_valid_from"))),
		},
		fields=["alfrom_date", "alto_date", "alfrom_hours", "alto_hours"],
	)
	for leave in leave_rows:
		start = getdate(leave.alfrom_date)
		end = getdate(leave.alto_date)
		current = max(start, getdate(_value(parent, "ts_valid_from")))
		last = min(end, getdate(_value(parent, "ts_valid_for")))
		while current <= last:
			if current not in holidays:
				if current == start and flt(leave.alfrom_hours) > 0:
					hours = flt(leave.alfrom_hours)
				elif current == end and end > start and flt(leave.alto_hours) > 0:
					hours = flt(leave.alto_hours)
				else:
					hours = reduced.get(current, flt(template.hours_on_date))
				leave_hours[current] += hours
			current += timedelta(days=1)
	return template, holidays, reduced, dict(leave_hours)


def _validate_daily_totals(
	parent: object,
	positions: list[object],
	template: object,
	holidays: set[object],
	reduced: dict[object, float],
	leave_hours: dict[object, float],
) -> list[str]:
	totals: dict[object, float] = defaultdict(float)
	for position in positions:
		for detail in _value(position, "table") or []:
			if _value(detail, "date"):
				totals[getdate(_value(detail, "date"))] += flt(_value(detail, "hours"))
	errors: list[str] = []
	current = getdate(_value(parent, "ts_valid_from"))
	end = getdate(_value(parent, "ts_valid_for"))
	while current <= end:
		if current not in holidays:
			expected = reduced.get(current, flt(_value(template, "hours_on_date")))
			minimum = expected - flt(_value(template, "minimum_hours"))
			maximum = expected + flt(_value(template, "maximum_hours"))
			total = totals.get(current, 0.0) + leave_hours.get(current, 0.0)
			if total < minimum:
				errors.append(
					_("{0}: total hours cannot be less than {1}").format(current, minimum)
				)
			if total > maximum:
				errors.append(
					_("{0}: total hours cannot exceed {1}").format(current, maximum)
				)
		current += timedelta(days=1)
	return errors


def _task_children(project: str, task: str) -> list[str]:
	children: list[str] = []
	pending = [task]
	seen = {task}
	while pending:
		direct = frappe.get_all(
			"Task",
			filters={"project": project, "parent_task": ("in", pending)},
			pluck="name",
		)
		pending = []
		for name in direct:
			if name not in seen:
				seen.add(name)
				children.append(name)
				pending.append(name)
	return children


def _root_task_with_issue(task_name: str) -> str | None:
	seen: set[str] = set()
	current = task_name
	while current and current not in seen:
		seen.add(current)
		row = frappe.db.get_value(
			"Task",
			current,
			["parent_task", "custom_linked_issue"],
			as_dict=True,
		)
		if not row:
			return None
		if row.custom_linked_issue:
			return current
		current = row.parent_task
	return None


def _find_plan(project: str, task_name: str, role: str, requirement: str) -> tuple[str, float] | None:
	root_issue = _root_task_with_issue(task_name) if requirement == "Обязательно для всех Запросов" else None
	seen: set[str] = set()
	current = task_name
	while current and current not in seen:
		seen.add(current)
		plan_name = frappe.db.get_value(
			"Project Work Efforts",
			{
				"pwe_project": project,
				"pwe_task": current,
				"pwe_project_role": role,
			},
			"name",
		)
		if plan_name:
			plan = frappe.get_doc("Project Work Efforts", plan_name)
			hours = sum(flt(row.pwea_plan) for row in plan.pwe_amount)
			if hours > 0:
				return current, hours
		if root_issue and current == root_issue:
			break
		current = frappe.db.get_value("Task", current, "parent_task")
	return None


def _validate_planned_limits(parent: object, positions: list[object]) -> list[str]:
	errors: list[str] = []
	for position in positions:
		project = str(_value(position, "project") or "")
		document_name = str(_value(position, "document_name") or "")
		role = str(_value(position, "project_role") or "")
		if not all((project, document_name, role)):
			continue
		task = document_name
		if _value(position, "document_type") == "Issue":
			task = (
				frappe.db.get_value(
					"Task",
					{"project": project, "custom_linked_issue": document_name},
					"name",
				)
				or ""
			)
		elif _value(position, "document_type") != "Task":
			continue
		if not task:
			continue
		requirement = (
			frappe.db.get_value(
				"Project",
				project,
				"custom_обязательность_плановых_трудозатрат",
			)
			or "Опционально"
		)
		root_issue = _root_task_with_issue(task)
		plan_required = requirement == "Обязательно для всех Задач" or (
			requirement == "Обязательно для всех Запросов" and root_issue
		)
		plan = _find_plan(project, task, role, requirement)
		if plan_required and not plan:
			errors.append(
				_("Task {0} has no required planned hours for role {1}").format(task, role)
			)
			continue
		if not plan:
			continue
		plan_task, planned_hours = plan
		fact_tasks = [plan_task, *_task_children(project, plan_task)]
		fact_issues = frappe.get_all(
			"Task",
			filters={
				"name": ("in", fact_tasks),
				"custom_linked_issue": ("is", "set"),
			},
			pluck="custom_linked_issue",
		)
		existing = sum(
			flt(row.all_hours)
			for row in (
				frappe.get_all(
					"User Timesheet Position",
					filters={
						"document_type": "Task",
						"document_name": ("in", fact_tasks),
						"project_role": role,
						"user_timesheet": ("!=", _value(parent, "name")),
					},
					fields=["all_hours"],
				)
				+ (
					frappe.get_all(
						"User Timesheet Position",
						filters={
							"document_type": "Issue",
							"document_name": ("in", fact_issues),
							"project_role": role,
							"user_timesheet": ("!=", _value(parent, "name")),
						},
						fields=["all_hours"],
					)
					if fact_issues
					else []
				)
			)
		)
		local = sum(
			sum(flt(_value(detail, "hours")) for detail in (_value(row, "table") or []))
			for row in positions
			if (
				_value(row, "document_type") == "Task"
				and _value(row, "document_name") in fact_tasks
				or _value(row, "document_type") == "Issue"
				and _value(row, "document_name") in fact_issues
			)
			and _value(row, "project_role") == role
		)
		block_limit = frappe.db.get_value(
			"Limit Control",
			{"parent": project, "parenttype": "Project", "type": "Блокировка"},
			"limit",
		)
		if block_limit and existing + local > planned_hours * flt(block_limit) / 100:
			errors.append(
				_("Task {0} exceeds the blocking planned-hours limit for role {1}").format(
					task,
					role,
				)
			)
	return list(dict.fromkeys(errors))


def _materialize_position(parent: object, payload: TimesheetPositionInput, existing: object | None):
	values = {
		"user_timesheet": _value(parent, "name"),
		"user": _value(parent, "timesheet_from"),
		"user_group": _value(parent, "user_group"),
		"project": payload.get("project"),
		"document_type": payload.get("document_type"),
		"document_name": payload.get("document_name"),
		"project_role": payload.get("project_role"),
		"reject_reason": "",
	}
	doc = existing or frappe.get_doc(
		{
			"doctype": "User Timesheet Position",
			"status": EDITING,
			"workflow_state": EDITING,
			**values,
		}
	)
	doc.update(values)
	details = payload.get("table") or payload.get("details") or []
	doc.set(
		"table",
		[
			{
				"date": _value(detail, "date"),
				"hours": flt(_value(detail, "hours")),
				"description": str(_value(detail, "description") or "").strip(),
			}
			for detail in details
		],
	)
	doc.all_hours = sum(flt(row.hours) for row in doc.table)
	return doc


def _prepare_positions(
	parent: object,
	payloads: list[TimesheetPositionInput],
	deleted_names: list[str],
) -> tuple[list[object], list[object]]:
	actual_names = sorted(
		frappe.get_all(
			"User Timesheet Position",
			filters={"user_timesheet": _value(parent, "name")},
			pluck="name",
			order_by="name asc",
		)
	)
	actual_set = set(actual_names)
	if not set(deleted_names).issubset(actual_set):
		raise frappe.PermissionError(_("A deleted position does not belong to this timesheet"))
	locked = {
		name: frappe.get_doc("User Timesheet Position", name, for_update=True)
		for name in actual_names
	}
	seen_existing: set[str] = set()
	docs: list[object] = []
	for payload in payloads:
		payload_name = payload.get("name")
		name = str(payload_name) if payload_name not in (None, "") else ""
		is_client_new = not name or name.isdigit() or cint(payload.get("new"))
		if name in actual_set:
			if name in deleted_names or name in seen_existing:
				raise frappe.ValidationError(_("Timesheet position payload is inconsistent"))
			seen_existing.add(name)
			docs.append(_materialize_position(parent, payload, locked[name]))
		elif is_client_new:
			docs.append(_materialize_position(parent, payload, None))
		else:
			raise frappe.PermissionError(_("A selected position does not belong to this timesheet"))
	expected_existing = actual_set - set(deleted_names)
	if seen_existing != expected_existing:
		raise frappe.ValidationError(
			_("Every retained timesheet position must be included in the request")
		)
	return docs, [locked[name] for name in deleted_names]


def _validate_positions(parent: object, positions: list[object]) -> None:
	errors = _validate_parent_period(parent)
	if errors:
		frappe.throw(
			"<br>".join(frappe.utils.escape_html(error) for error in errors),
			frappe.ValidationError,
			title=_("Timesheet filling errors"),
		)
	if not positions:
		return
	template, holidays, reduced, leave_hours = _calendar_context(parent)
	for position in positions:
		errors.extend(
			_validate_position_shape(
				parent,
				position,
				description_required=bool(template._is_mandatory),
			)
		)
		errors.extend(_validate_position_links(parent, position, template))
	errors.extend(
		_validate_daily_totals(
			parent,
			positions,
			template,
			holidays,
			reduced,
			leave_hours,
		)
	)
	errors.extend(_validate_planned_limits(parent, positions))
	if errors:
		frappe.throw(
			"<br>".join(frappe.utils.escape_html(error) for error in dict.fromkeys(errors)),
			frappe.ValidationError,
			title=_("Timesheet filling errors"),
		)


def lock_dependencies(doctype: str, name: str) -> list[tuple[str, str]]:
	if doctype != "User Timesheet Position":
		return []
	parent = frappe.db.get_value("User Timesheet Position", name, "user_timesheet")
	return [("User Timesheet", parent)] if parent else []


def pending_approvers(doctype: str, name: str):
	"""Aggregate active child-position approvers for a parent timesheet."""
	if doctype != "User Timesheet":
		return None
	position_names = frappe.get_all(
		"User Timesheet Position",
		filters={"user_timesheet": name},
		pluck="name",
	)
	if not position_names:
		return []
	return frappe.get_all(
		"Workflow Task",
		filters={
			"reference_doctype": "User Timesheet Position",
			"reference_name": ("in", position_names),
			"status": "Working",
			"round_status": "Open",
		},
		fields=["approver", "approval_round_id", "workflow_state", "reference_name"],
		order_by="approver asc, reference_name asc",
	)


def digest_item(task):
	if task.reference_doctype != "User Timesheet Position":
		return None
	parent = frappe.db.get_value(
		"User Timesheet Position",
		task.reference_name,
		"user_timesheet",
	)
	if not parent:
		return None
	from frappe.utils import get_url_to_form

	return {
		"group_key": f"User Timesheet:{parent}",
		"doctype": "User Timesheet",
		"name": parent,
		"title": parent,
		"link": get_url_to_form("User Timesheet", parent),
		"actions": [],
	}


@frappe.whitelist()
def get_timesheet_approval_actions(timesheet_name: str) -> dict[str, object]:
	parent = frappe.get_doc("User Timesheet", timesheet_name)
	parent.check_permission("read")
	position_names = set(
		frappe.get_all(
			"User Timesheet Position",
			filters={"user_timesheet": parent.name},
			pluck="name",
		)
	)
	from dinext_common.workflow_approval.api import get_my_queue

	tasks = [
		task
		for task in get_my_queue(limit=1000)
		if task["reference_doctype"] == "User Timesheet Position"
		and task["reference_name"] in position_names
	]
	action_sets = [
		{row["action"] for row in task["available_transitions"]}
		for task in tasks
	]
	common_actions = sorted(set.intersection(*action_sets)) if action_sets else []
	required = {
		row["action"]
		for task in tasks
		for row in task["available_transitions"]
		if row["comment_is_required"]
	}
	return {
		"tasks": [task["name"] for task in tasks],
		"position_count": len({task["reference_name"] for task in tasks}),
		"actions": [
			{"action": action, "comment_is_required": action in required}
			for action in common_actions
		],
	}


@frappe.whitelist(methods=["POST"])
def vote_timesheet_positions(
	timesheet_name: str,
	action: str,
	comment: object = None,
	request_id: str | None = None,
) -> dict[str, object]:
	parent = frappe.get_doc("User Timesheet", timesheet_name, for_update=True)
	parent.check_permission("read")
	frappe.flags.timesheet_transition_messages = []
	frappe.flags.workflow_finalization_errors = []
	available = get_timesheet_approval_actions(parent.name)
	if action not in {row["action"] for row in available["actions"]}:
		frappe.throw(_("The action is not available for all selected positions"))
	from dinext_common.workflow_approval.engine import (
		WorkflowApprovalConflictError,
		cast_vote,
	)

	results = []
	for index, task_name in enumerate(sorted(available["tasks"])):
		# The first vote can move the whole timesheet and cancel the other tasks.
		if _task_no_longer_matches_source(task_name):
			continue
		try:
			results.append(
				cast_vote(
					task_name,
					action=action,
					comment=comment,
					request_id=f"{request_id or frappe.generate_hash(length=16)}:{index}",
					completion_source="Bulk",
				)
			)
		except WorkflowApprovalConflictError as caught:
			if not any(row.get("transitioned") for row in results):
				raise
			_note_timesheet_transition_message(str(caught))
	messages = [
		*(getattr(frappe.flags, "workflow_finalization_errors", None) or []),
		*(getattr(frappe.flags, "timesheet_transition_messages", None) or []),
	]
	return {"timesheet": parent.name, "results": results, "messages": messages}


def on_vote_completed(task, source, transition) -> None:
	if (
		source.doctype == "User Timesheet Position"
		and transition.next_state == REJECTED
		and task.vote_comment
	):
		source.reject_reason = task.vote_comment
		frappe.db.set_value(
			source.doctype,
			source.name,
			"reject_reason",
			task.vote_comment,
			update_modified=False,
		)


@frappe.whitelist(methods=["POST"])
def orchestrate_timesheet(
	ts_name: str,
	operation: TimesheetOperation,
	positions: object = None,
	deleted_positions: object = None,
) -> TimesheetOrchestrationResponse:
	"""Validate, persist, and transition one complete User Timesheet aggregate."""
	parent = frappe.get_doc("User Timesheet", ts_name, for_update=True)
	actor = frappe.session.user
	_authorize_operation(parent, operation, actor=actor)
	payloads = _parse_positions(positions)
	deleted_names = _parse_names(deleted_positions)
	position_docs, deleted_docs = _prepare_positions(parent, payloads, deleted_names)
	_validate_positions(parent, position_docs)
	for doc in sorted(deleted_docs, key=lambda row: row.name):
		doc.delete(ignore_permissions=True)
	persisted: list[object] = []
	for doc in sorted(position_docs, key=lambda row: str(row.name or "")):
		if doc.is_new():
			doc.insert(ignore_permissions=True)
		else:
			doc.save(ignore_permissions=True)
		persisted.append(doc)
	parent_status, position_status = _operation_states(
		operation,
		has_positions=bool(persisted),
	)
	if position_status:
		from dinext_common.workflow_approval.engine import apply_domain_transition

		transition_actor = _domain_transition_actor(actor)
		for position in sorted(persisted, key=lambda row: row.name):
			apply_domain_transition(
				"User Timesheet Position",
				position.name,
				position_status,
				reason=_("Timesheet operation {0} from parent {1}").format(
					operation,
					parent.name,
				),
				actor=transition_actor,
			)
	parent.reload()
	if (
		operation == "Start"
		and persisted
		and not frappe.db.count(
			"User Timesheet Position",
			{
				"user_timesheet": parent.name,
				"status": ("!=", POSITION_APPROVED),
			},
		)
	):
		parent_status = PARENT_APPROVED
	parent.ut_status = parent_status
	if parent_status == PARENT_APPROVED:
		parent.ut_approval_date = nowdate()
	else:
		parent.ut_approval_date = None
	parent.save(ignore_permissions=True)
	return {
		"timesheet": parent.name,
		"status": parent.ut_status,
		"processed": len(persisted),
		"positions": [doc.name for doc in persisted],
	}


def on_utp_update(doc, method=None) -> None:
	if not _enabled():
		return
	old = doc.get_doc_before_save()
	old_status = old.status if old else None
	if old_status == doc.status:
		return
	parent = frappe.get_doc("User Timesheet", doc.user_timesheet, for_update=True)
	if not getattr(frappe.flags, "in_timesheet_approval_cascade", False):
		_recalculate_parent(parent, doc, old_status)
	if (
		doc.document_type == "Task"
		and doc.document_name
		and ((doc.status == POSITION_APPROVED) != (old_status == POSITION_APPROVED))
	):
		recalculate_task_actual_dates(doc.document_name)
	if old_status != PENDING and doc.status == PENDING:
		frappe.enqueue(
			notify_task_limit_if_pending,
			position_name=doc.name,
			queue="short",
			enqueue_after_commit=True,
			now=frappe.flags.in_test,
		)


def _task_no_longer_matches_source(task_name: str) -> bool:
	task = frappe.db.get_value(
		"Workflow Task",
		task_name,
		[
			"status",
			"round_status",
			"reference_doctype",
			"reference_name",
			"workflow_state",
		],
		as_dict=True,
	)
	if not task or task.status != "Working" or task.round_status != "Open":
		return True
	from frappe.model.workflow import get_workflow

	state_field = get_workflow(task.reference_doctype).workflow_state_field
	current_state = frappe.db.get_value(
		task.reference_doctype,
		task.reference_name,
		state_field,
	)
	return str(current_state or "") != str(task.workflow_state or "")


def _note_timesheet_transition_message(message: str) -> None:
	notes = getattr(frappe.flags, "timesheet_transition_messages", None)
	if not isinstance(notes, list):
		notes = []
		frappe.flags.timesheet_transition_messages = notes
	notes.append(str(message))


def load_position_statuses(timesheet_name: str) -> list[str]:
	return frappe.get_all(
		"User Timesheet Position",
		filters={"user_timesheet": timesheet_name},
		pluck="status",
	)


def _recalculate_parent(parent, changed_position, old_status: str | None) -> None:
	del old_status
	from dinext_timesheets.timesheet_settings import (
		matching_position_rule,
		parent_position_target,
	)

	statuses = list(load_position_statuses(parent.name) or [])
	if changed_position.status and changed_position.status not in statuses:
		statuses.append(changed_position.status)
	counts: dict[str, int] = {}
	for status in statuses:
		if not status:
			continue
		counts[status] = counts.get(status, 0) + 1
	rule = matching_position_rule(counts)
	if not rule or parent.ut_status == rule["timesheet_status"]:
		return
	new_status = rule["timesheet_status"]
	parent.ut_status = new_status
	if new_status == PARENT_APPROVED:
		parent.ut_approval_date = nowdate()
	elif new_status == PENDING:
		parent.ut_approval_date = None
	target = parent_position_target(new_status)
	if not target:
		parent.save(ignore_permissions=True)
		return
	from dinext_common.workflow_approval.engine import apply_domain_transition

	frappe.flags.in_timesheet_approval_cascade = True
	try:
		parent.save(ignore_permissions=True)
		siblings = frappe.get_all(
			"User Timesheet Position",
			filters={
				"user_timesheet": parent.name,
				"name": ("!=", changed_position.name),
				"workflow_state": ("!=", target),
			},
			pluck="name",
			order_by="name asc",
		)
		for sibling_name in siblings:
			try:
				apply_domain_transition(
					"User Timesheet Position",
					sibling_name,
					target,
					reason=_("Timesheet returned for rework"),
					actor=frappe.session.user,
				)
			except Exception:
				frappe.log_error(
					title=f"Timesheet sibling transition failed: {sibling_name}",
				)
				_note_timesheet_transition_message(
					_("Could not update a related timesheet position: {0}").format(
						sibling_name
					)
				)
	finally:
		frappe.flags.in_timesheet_approval_cascade = False


def _linked_issue_dates(task_doc) -> tuple[object, object]:
	if task_doc.get("type") != "Issue" or not task_doc.get("custom_linked_issue"):
		return None, None
	meta = frappe.get_meta("Issue")
	resolution_field = (
		"resolution_date"
		if meta.has_field("resolution_date")
		else "sla_resolution_date"
		if meta.has_field("sla_resolution_date")
		else None
	)
	fields = ["opening_date", *([resolution_field] if resolution_field else [])]
	row = frappe.db.get_value(
		"Issue",
		task_doc.custom_linked_issue,
		fields,
		as_dict=True,
	)
	return (
		row.get("opening_date") if row else None,
		row.get(resolution_field) if row and resolution_field else None,
	)


def recalculate_task_actual_dates(task_name: str) -> None:
	"""Expand Task actual dates from all approved UTP rows without narrowing history."""
	positions = frappe.get_all(
		"User Timesheet Position",
		filters={
			"document_type": "Task",
			"document_name": task_name,
			"status": POSITION_APPROVED,
		},
		pluck="name",
	)
	actual_dates = []
	for position_name in positions:
		position = frappe.get_doc("User Timesheet Position", position_name)
		actual_dates.extend(
			getdate(row.date)
			for row in position.table
			if row.date and flt(row.hours) > 0
		)
	new_start = min(actual_dates) if actual_dates else None
	new_end = max(actual_dates) if actual_dates else None
	task = frappe.get_doc("Task", task_name)
	if task.completed_on:
		completed_on = getdate(task.completed_on)
		new_end = max(filter(None, (new_end, completed_on)))
	current_start = task.act_start_date
	current_end = task.act_end_date
	protected_start = current_start
	protected_end = current_end
	issue_start, issue_end = _linked_issue_dates(task)
	if (
		issue_start
		and str(current_start or "") == str(issue_start)
		and str(current_end or "") == str(getdate(issue_end) if issue_end else "")
		and (str(new_start or ""), str(new_end or ""))
		!= (str(current_start or ""), str(current_end or ""))
	):
		protected_start = protected_end = None
	if not new_start and not new_end:
		return
	if protected_start and (not new_start or getdate(new_start) > getdate(protected_start)):
		return
	if protected_end and (not new_end or getdate(new_end) < getdate(protected_end)):
		return
	if (str(current_start or ""), str(current_end or "")) == (
		str(new_start or ""),
		str(new_end or ""),
	):
		return
	task.act_start_date = new_start
	task.act_end_date = new_end
	_save_system_task(task)


def _save_system_task(task) -> None:
	"""Actual dates follow approval. The closing approver is not editing the WBS."""
	previous = frappe.session.user
	try:
		if previous != "Administrator":
			frappe.set_user("Administrator")
		task.save(ignore_permissions=True)
	finally:
		if frappe.session.user != previous:
			frappe.set_user(previous)


def mirror_utp_comment(doc, method=None) -> None:
	if not _enabled() or doc.reference_doctype != "User Timesheet Position":
		return
	parent = frappe.db.get_value(
		"User Timesheet Position",
		doc.reference_name,
		"user_timesheet",
	)
	if not parent:
		return
	comment = frappe.new_doc("Comment")
	comment.reference_doctype = "User Timesheet"
	comment.reference_name = parent
	comment.subject = doc.subject
	comment.comment_type = doc.comment_type
	comment.comment_email = doc.comment_email
	comment.comment_by = doc.comment_by
	comment.published = doc.published
	comment.seen = doc.seen
	comment.content = f"{doc.reference_name}: {doc.content}"
	comment.insert(ignore_permissions=True)


def notify_task_limit_if_pending(position_name: str) -> None:
	"""Recheck committed round before emitting the retained limit Notification."""
	if not frappe.db.exists(
		"Workflow Task",
		{
			"reference_doctype": "User Timesheet Position",
			"reference_name": position_name,
			"status": "Working",
			"round_status": "Open",
		},
	):
		return
	position = frappe.get_doc("User Timesheet Position", position_name)
	if position.status != PENDING:
		return
	managers = frappe.get_all(
		"Project Team Details",
		filters={"parent": position.project, "notifications_on_limits": 1},
		pluck="pt_participant",
	)
	if not managers:
		return
	frappe.call(
		"calculate_timesheet_limits",
		positions=json.dumps(
			[
				{
					"document_name": position.document_name,
					"project_role": position.project_role,
					"project": position.project,
					"status": position.status,
				}
			]
		),
		timesheet_name=position.user_timesheet,
	)
	result_rows = frappe.response.get("message") or []
	if not result_rows or not result_rows[0].get("planned_hours"):
		return
	result = result_rows[0]
	limit = frappe.db.get_value(
		"Limit Control",
		{
			"parent": position.project,
			"type": "Уведомление",
			"view": "Notification",
		},
		["limit", "notification"],
		as_dict=True,
	)
	if not limit:
		return
	percentage = result["total_hours"] / result["planned_hours"] * 100
	if percentage <= limit.limit:
		return
	notification = frappe.get_doc("Notification", limit.notification)
	context = {
		"completion_percentage": percentage,
		"actual_hours": result["total_hours"],
		"planned_hours": result["planned_hours"],
		"timesheet_position": position.name,
		"task_name": position.document_name,
		"project": position.project,
		"project_role": position.project_role,
	}
	for manager in managers:
		todo = frappe.new_doc("ToDo")
		todo.description = _("Timesheet limit exceeded")
		todo.allocated_to = manager
		todo.reference_type = "User Timesheet Position"
		todo.reference_name = position.name
		todo.flags.context = context
		notification.send(todo)
