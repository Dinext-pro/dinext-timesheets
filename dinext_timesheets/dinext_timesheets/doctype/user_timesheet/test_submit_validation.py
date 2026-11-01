# Copyright (c) 2026, Dinext and Contributors
# See license.txt

import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from dinext_timesheets import workflow_approval

_UNSET = object()


def _texts(errors):
	return [str(error) for error in errors]


def _parent(**overrides):
	values = {
		"name": "UT-1",
		"timesheet_from": "owner@example.com",
		"ts_valid_from": "2026-09-01",
		"ts_valid_for": "2026-09-07",
	}
	values.update(overrides)
	return SimpleNamespace(**values)


def _position(**overrides):
	values = {
		"name": "UTP-1",
		"project": "PROJ-1",
		"document_type": "Task",
		"document_name": "TASK-1",
		"project_role": "Developer",
	}
	values.update(overrides)
	return SimpleNamespace(**values)


def _template(*doctypes):
	return SimpleNamespace(
		doctype_for_timesheet=[SimpleNamespace(dtdoctype=name) for name in doctypes]
	)


class TestSubmitValidation(FrappeTestCase):
	def test_period_requires_both_dates(self):
		for missing in (
			{"ts_valid_from": None},
			{"ts_valid_for": None},
			{"ts_valid_from": None, "ts_valid_for": None},
		):
			with self.subTest(missing=missing):
				self.assertEqual(
					_texts(workflow_approval._validate_parent_period(_parent(**missing))),
					["Timesheet start and end dates are required"],
				)

	def test_period_start_cannot_follow_the_end(self):
		errors = workflow_approval._validate_parent_period(
			_parent(ts_valid_from="2026-09-08", ts_valid_for="2026-09-01")
		)
		self.assertEqual(
			_texts(errors),
			["Timesheet start date cannot be after its end date"],
		)

	def test_overlapping_timesheet_is_rejected(self):
		with patch.object(frappe, "get_all", return_value=["UT-2"]):
			errors = workflow_approval._validate_parent_period(_parent())
		self.assertEqual(_texts(errors), ["Another timesheet overlaps this period"])

	def test_owner_without_worker_is_rejected(self):
		self._assert_calendar_error(
			"Timesheet owner has no Worker record",
			worker_name=None,
		)

	def test_worker_without_template_is_rejected(self):
		self._assert_calendar_error(
			"Worker has no Timesheet Template",
			template_name=None,
		)

	def test_worker_without_holiday_list_is_rejected(self):
		self._assert_calendar_error(
			"Worker has no Holiday List",
			holiday_list_name=None,
		)

	def test_holiday_list_must_cover_the_period(self):
		cases = (
			None,
			frappe._dict(from_date=None, to_date="2026-12-31"),
			frappe._dict(from_date="2026-09-02", to_date="2026-12-31"),
			frappe._dict(from_date="2026-01-01", to_date="2026-09-06"),
		)
		for holiday_list in cases:
			with self.subTest(holiday_list=holiday_list):
				self._assert_calendar_error(
					"Holiday List is not active for the whole timesheet period",
					holiday_list=holiday_list,
				)

	def test_working_hours_must_cover_the_period(self):
		cases = (
			None,
			frappe._dict(hod_from_date=None, hod_to_date="2026-12-31"),
			frappe._dict(hod_from_date="2026-09-02", hod_to_date="2026-12-31"),
			frappe._dict(hod_from_date="2026-01-01", hod_to_date="2026-09-06"),
		)
		for working_hours in cases:
			with self.subTest(working_hours=working_hours):
				self._assert_calendar_error(
					"Working Hours On Date is not active for the whole timesheet period",
					working_hours_name="WH-1",
					working_hours=working_hours,
				)

	def test_position_date_is_required(self):
		errors = workflow_approval._validate_position_shape(
			_parent(),
			_position(
				table=[SimpleNamespace(date=None, hours=1, description="done")]
			),
			description_required=True,
		)
		self.assertEqual(
			_texts(errors),
			[
				"Position UTP-1: date is required",
				"Position UTP-1: total hours must be positive",
			],
		)

	def test_position_rejects_a_duplicate_date(self):
		errors = workflow_approval._validate_position_shape(
			_parent(),
			_position(
				table=[
					SimpleNamespace(date="2026-09-02", hours=1, description="am"),
					SimpleNamespace(date="2026-09-02", hours=1, description="pm"),
				]
			),
			description_required=True,
		)
		self.assertEqual(
			_texts(errors),
			["Position UTP-1: duplicate date 2026-09-02"],
		)

	def test_position_total_hours_must_be_positive(self):
		errors = workflow_approval._validate_position_shape(
			_parent(),
			_position(table=[]),
			description_required=False,
		)
		self.assertEqual(
			_texts(errors),
			["Position UTP-1: total hours must be positive"],
		)

	def test_linked_position_with_a_covered_task_is_accepted(self):
		self.assertEqual(self._link_errors(), [])

	def test_inactive_project_is_rejected(self):
		for project in (
			None,
			{"status": "Completed", "is_active": "Yes"},
			{"status": "Open", "is_active": "No"},
		):
			with self.subTest(project=project):
				self.assertEqual(
					self._link_errors(project=project),
					["Position UTP-1: project is not active and open"],
				)

	def test_document_type_must_be_enabled_by_the_template(self):
		self.assertEqual(
			self._link_errors(doctypes=("Issue",)),
			[
				"Position UTP-1: document type is not enabled by the timesheet template"
			],
		)

	def test_unknown_project_role_is_rejected(self):
		self.assertEqual(
			self._link_errors(role_exists=False),
			["Position UTP-1: project role does not exist"],
		)

	def test_task_from_another_project_is_rejected(self):
		self.assertEqual(
			self._link_errors(task={"project": "OTHER"}),
			[
				"Position UTP-1: task or issue does not belong to the selected project"
			],
		)

	def test_ineligible_task_is_rejected(self):
		for task in (
			{"status": "Cancelled"},
			{"status": "Template"},
			{"is_milestone": 1},
		):
			with self.subTest(task=task):
				self.assertEqual(
					self._link_errors(task=task),
					["Position UTP-1: task is not eligible for timesheets"],
				)

	def test_task_outside_the_timesheet_period_is_rejected(self):
		self.assertEqual(
			self._link_errors(task={"exp_end_date": "2026-08-01"}),
			["Position UTP-1: task is outside the timesheet period"],
		)

	def test_unassigned_task_is_rejected(self):
		self.assertEqual(
			self._link_errors(assigned=False, shared=False),
			[
				"Position UTP-1: task or issue is not assigned or shared with the owner"
			],
		)

	def test_role_outside_the_owner_period_is_rejected(self):
		self.assertEqual(
			self._link_errors(team=False),
			["Position UTP-1: project role is not valid for the owner and period"],
		)

	def test_daily_total_below_the_minimum_is_rejected(self):
		errors = self._daily_errors(hours=7)
		self.assertEqual(
			_texts(errors),
			["2026-09-01: total hours cannot be less than 8.0"],
		)

	def test_daily_total_above_the_maximum_is_rejected(self):
		errors = self._daily_errors(hours=9)
		self.assertEqual(
			_texts(errors),
			["2026-09-01: total hours cannot exceed 8.0"],
		)

	def test_request_plan_is_required_only_with_a_root_issue(self):
		with_root = self._request_plan_errors(root_issue="ROOT-1")
		without_root = self._request_plan_errors(root_issue=None)
		self.assertEqual(
			_texts(with_root),
			["Task TASK-1 has no required planned hours for role Developer"],
		)
		self.assertEqual(without_root, [])

	def test_client_submit_errors_run_under_node(self):
		app_root = Path(frappe.get_app_path("dinext_timesheets")).resolve().parent
		script = app_root / "tests" / "js" / "submit_errors.test.mjs"
		result = subprocess.run(
			[
				"node",
				"--experimental-default-type=module",
				"--test",
				str(script),
			],
			cwd=app_root,
			capture_output=True,
			text=True,
			check=False,
		)
		self.assertEqual(
			result.returncode,
			0,
			result.stdout + "\n" + result.stderr,
		)

	def _assert_calendar_error(self, message, **options):
		with self.assertRaises(frappe.ValidationError) as caught:
			self._calendar_context(**options)
		self.assertEqual(str(caught.exception), message)

	def _calendar_context(
		self,
		*,
		worker_name="WORKER-1",
		template_name="TEMPLATE-1",
		holiday_list_name="HOLIDAYS",
		holiday_list=_UNSET,
		working_hours_name=None,
		working_hours=None,
	):
		if holiday_list is _UNSET and holiday_list_name:
			holiday_list = frappe._dict(from_date="2026-01-01", to_date="2026-12-31")
		worker = SimpleNamespace(
			wtimesheet_template=template_name,
			wholiday_list=holiday_list_name,
		)
		template = SimpleNamespace(tt_working_hours_on_date=working_hours_name)

		def get_value(doctype, *_args, **_kwargs):
			if doctype == "Worker":
				return worker_name
			if doctype == "Holiday List":
				return holiday_list
			if doctype == "Working Hours On Date":
				return working_hours
			return None

		with (
			patch.object(frappe.db, "get_value", side_effect=get_value),
			patch.object(frappe, "get_doc", side_effect=[worker, template]),
			patch.object(frappe, "get_all", return_value=[]),
		):
			return workflow_approval._calendar_context(_parent())

	def _daily_errors(self, hours):
		parent = _parent(ts_valid_from="2026-09-01", ts_valid_for="2026-09-01")
		template = SimpleNamespace(hours_on_date=8, minimum_hours=0, maximum_hours=0)
		positions = [
			SimpleNamespace(table=[SimpleNamespace(date="2026-09-01", hours=hours)])
		]
		return workflow_approval._validate_daily_totals(
			parent,
			positions,
			template,
			holidays=set(),
			reduced={},
			leave_hours={},
		)

	def _request_plan_errors(self, root_issue):
		position = _position(table=[])

		def get_value(_doctype, _name, fieldname=None, **_kwargs):
			if fieldname == "custom_обязательность_плановых_трудозатрат":
				return "Обязательно для всех Запросов"
			return None

		with (
			patch.object(frappe.db, "get_value", side_effect=get_value),
			patch.object(workflow_approval, "_find_plan", return_value=None),
			patch.object(
				workflow_approval,
				"_root_task_with_issue",
				return_value=root_issue,
			),
		):
			return workflow_approval._validate_planned_limits(_parent(), [position])

	def _link_errors(
		self,
		*,
		project=_UNSET,
		task=None,
		doctypes=("Task",),
		role_exists=True,
		assigned=True,
		shared=False,
		team=True,
	):
		return self._link_errors_with(
			project_row=self._project_row(project),
			task_row=self._task_row(task),
			doctypes=doctypes,
			role_exists=role_exists,
			assigned=assigned,
			shared=shared,
			team=team,
		)

	def _project_row(self, project):
		if project is None:
			return None
		row = {
			"name": "PROJ-1",
			"status": "Open",
			"is_active": "Yes",
			"expected_start_date": "2026-01-01",
			"expected_end_date": "2026-12-31",
		}
		if project is not _UNSET:
			row.update(project)
		return frappe._dict(row)

	def _task_row(self, task):
		row = {
			"project": "PROJ-1",
			"custom_include": 1,
			"status": "Open",
			"is_milestone": 0,
			"exp_start_date": "2026-01-01",
			"exp_end_date": "2026-12-31",
			"completed_on": None,
		}
		if task:
			row.update(task)
		return frappe._dict(row)

	def _link_errors_with(
		self,
		*,
		project_row,
		task_row,
		doctypes,
		role_exists,
		assigned,
		shared,
		team,
	):
		def get_value(doctype, _name, _fields=None, **_kwargs):
			if doctype == "Project":
				return project_row
			if doctype == "Task":
				return task_row
			return None

		def exists(doctype, _name=None, **_kwargs):
			if doctype == "Project Role":
				return role_exists
			if doctype == "ToDo":
				return assigned
			if doctype == "DocShare":
				return shared
			return False

		team_rows = (
			[{"pt_valid_from": "2026-01-01", "pt_valid_for": "2026-12-31"}]
			if team
			else []
		)
		with (
			patch.object(frappe.db, "get_value", side_effect=get_value),
			patch.object(frappe.db, "exists", side_effect=exists),
			patch.object(
				workflow_approval,
				"_participant_values",
				return_value={"owner@example.com"},
			),
			patch.object(frappe, "get_all", return_value=team_rows),
		):
			return _texts(
				workflow_approval._validate_position_links(
					_parent(),
					_position(),
					_template(*doctypes),
				)
			)
