# Copyright (c) 2026, Dinext and contributors
# See license.txt

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

import frappe

from dinext_timesheets import application_for_leave, hooks
from dinext_timesheets.dinext_timesheets.doctype.application_for_leave.application_for_leave import (
	ApplicationForLeave,
)


class LeaveDocument(frappe._dict):
	def is_new(self) -> bool:
		return bool(self.get("__islocal"))


class TestApplicationForLeave(TestCase):
	def setUp(self):
		self.enterContext(patch.object(frappe, "flags", frappe._dict(mute_messages=True)))
		self.enterContext(patch("frappe.translate.get_all_translations", return_value={}))
		self.enterContext(patch.object(frappe, "get_hooks", return_value={}))

	def test_a_single_controller_owns_document_validation(self):
		self.assertTrue(callable(getattr(ApplicationForLeave, "before_validate", None)))
		self.assertTrue(callable(getattr(ApplicationForLeave, "validate", None)))
		self.assertEqual(
			hooks.workflow_approval_domain_handlers["Application For Leave"]["validate_vote"],
			"dinext_timesheets.application_for_leave.validate_workflow_vote",
		)

	def test_validation_calls_the_project_provider_after_calculating_hours(self):
		doc = frappe._dict(
			alfrom_date="2026-01-05",
			alto_date="2026-01-06",
			alworker="WORKER",
			alfrom_hours=5,
			alto_hours=4,
			status="Pending Approval",
		)
		records = {
			("Worker", "WORKER"): frappe._dict(
				wuser="worker@example.com", wholiday_list="HOLIDAYS", wtimesheet_template="TEMPLATE"
			),
			("Holiday List", "HOLIDAYS"): frappe._dict(
				from_date="2026-01-01", to_date="2026-12-31", holidays=[]
			),
			("Timesheet Template", "TEMPLATE"): frappe._dict(
				hours_on_date=8, tt_working_hours_on_date="WORKING-HOURS"
			),
			("Working Hours On Date", "WORKING-HOURS"): frappe._dict(
				hod_from_date="2026-01-01", hod_to_date="2026-12-31"
			),
		}

		def rebuild(document, start, end):
			self.assertEqual((start, end), (date(2026, 1, 5), date(2026, 1, 6)))
			document.user_projects = [document.lauser, document.al_total_hours]

		for project_hooks in ({}, {"rebuild": ["test.rebuild"]}):
			with (
				self.subTest(project_hooks=project_hooks),
				patch.object(
					frappe, "get_doc", side_effect=lambda doctype, name, **kwargs: records[(doctype, name)]
				),
				patch.object(frappe, "get_hooks", return_value=project_hooks),
				patch.object(frappe, "get_attr", return_value=rebuild),
			):
				doc.user_projects = []
				ApplicationForLeave.validate(doc)
				self.assertEqual(doc.al_total_hours, 9)
				self.assertEqual(doc.user_projects, ["worker@example.com", 9] if project_hooks else [])

	def test_only_superseded_leave_scripts_are_disabled(self):
		from dinext_timesheets.setup import application_for_leave

		rows = {"AFL_Calculate_Hours": 0, "AFL_Projects": 0, "Site customization": 0}

		def get_all(doctype, *, filters, pluck):
			names = filters["name"][1]
			return [name for name in names if rows.get(name) == filters["disabled"]]

		def set_value(doctype, name, field, value, *, update_modified):
			rows[name] = value

		cache = Mock()
		with (
			patch.object(frappe, "get_all", side_effect=get_all),
			patch.object(frappe, "db", SimpleNamespace(set_value=set_value)),
			patch.object(frappe, "cache", cache),
		):
			application_for_leave.disable_superseded_server_scripts()
			application_for_leave.disable_superseded_server_scripts()
		self.assertEqual(rows, {"AFL_Calculate_Hours": 1, "AFL_Projects": 1, "Site customization": 0})
		cache.delete_value.assert_called_once_with("server_script_map")

	def test_dates_are_required_and_ordered(self):
		for values in (
			{"alfrom_date": None, "alto_date": "2026-01-05"},
			{"alfrom_date": "2026-01-05", "alto_date": None},
			{"alfrom_date": "2026-01-06", "alto_date": "2026-01-05"},
		):
			with self.subTest(values=values), self.assertRaises(frappe.ValidationError):
				ApplicationForLeave.validate(LeaveDocument(**values))

	def test_requires_the_workers_user_before_calculating_hours_or_projects(self):
		for worker_user in (None, "worker@example.com"):
			with self.subTest(worker_user=worker_user):
				doc = LeaveDocument(
					alfrom_date="2026-01-05",
					alto_date="2026-01-06",
					alworker="WRKR-1",
					lauser="other@example.com",
					status="Pending Approval",
					user_projects=[frappe._dict(project="BEFORE")],
				)
				worker = frappe._dict(wuser=worker_user, wholiday_list="RU Holidays")

				def get_doc(doctype, name, **kwargs):
					self.assertEqual((doctype, name), ("Worker", "WRKR-1"))
					return worker

				with (
					patch("frappe.get_doc", side_effect=get_doc),
					self.assertRaises(frappe.ValidationError),
				):
					ApplicationForLeave.validate(doc)

				self.assertIsNone(doc.al_total_hours)
				self.assertEqual(doc.user_projects, [{"project": "BEFORE"}])

	def test_rejects_negative_hours(self):
		for field in ("alfrom_hours", "alto_hours"):
			doc = LeaveDocument(
				alfrom_date="2026-01-05",
				alto_date="2026-01-06",
				alworker="WRKR-1",
				alfrom_hours=5,
				alto_hours=3,
			)
			doc[field] = -1
			worker = frappe._dict(wuser="worker@example.com")
			with (
				self.subTest(field=field),
				patch("frappe.get_doc", return_value=worker),
				self.assertRaisesRegex(frappe.ValidationError, "Leave hours cannot be negative"),
			):
				ApplicationForLeave.validate(doc)

	def test_calculates_hours_with_holidays_overrides_and_boundary_clamps(self):
		doc = LeaveDocument(
			alfrom_date="2026-01-05",
			alto_date="2026-01-08",
			alworker="WRKR-1",
			lauser=None,
			alfrom_hours=10,
			alto_hours=3,
		)
		worker = frappe._dict(
			name="WRKR-1",
			wuser="worker@example.com",
			wholiday_list="RU Holidays",
			wtimesheet_template="RU Template",
		)
		holiday_list = frappe._dict(
			name="RU Holidays",
			from_date=date(2026, 1, 1),
			to_date=date(2026, 12, 31),
			holidays=[frappe._dict(holiday_date=date(2026, 1, 6))],
		)
		template = frappe._dict(
			name="RU Template",
			hours_on_date=8,
			tt_working_hours_on_date="RU Short Days",
		)
		hours_on_date = frappe._dict(
			name="RU Short Days",
			hod_from_date=date(2026, 1, 1),
			hod_to_date=date(2026, 12, 31),
			hod_working_hours_table=[
				frappe._dict(wht_date=date(2026, 1, 7), wht_hours=6),
			],
		)
		documents = {
			("Worker", "WRKR-1"): worker,
			("Holiday List", "RU Holidays"): holiday_list,
			("Timesheet Template", "RU Template"): template,
			("Working Hours On Date", "RU Short Days"): hours_on_date,
		}

		with patch(
			"frappe.get_doc",
			side_effect=lambda doctype, name, **kwargs: documents[(doctype, name)],
		):
			ApplicationForLeave.validate(doc)

		self.assertEqual(doc.lauser, "worker@example.com")
		self.assertEqual(doc.alfrom_hours, 8)
		self.assertEqual(doc.alto_hours, 3)
		self.assertEqual(doc.al_total_hours, 17)

		for holidays, expected in (
			((date(2026, 1, 5), date(2026, 1, 6)), (0, 3, 9)),
			((date(2026, 1, 6), date(2026, 1, 8)), (8, 0, 14)),
			((date(2026, 1, 5), date(2026, 1, 8)), (0, 0, 14)),
		):
			with self.subTest(holidays=holidays):
				doc.alfrom_hours = 10
				doc.alto_hours = 3
				holiday_list.holidays = [frappe._dict(holiday_date=day) for day in holidays]
				with patch(
					"frappe.get_doc",
					side_effect=lambda doctype, name, **kwargs: documents[(doctype, name)],
				):
					ApplicationForLeave.validate(doc)

				self.assertEqual((doc.alfrom_hours, doc.alto_hours, doc.al_total_hours), expected)

	def test_overlapping_applications_include_boundary_dates_and_exclude_only_self_and_cancelled(self):
		doc = LeaveDocument(
			name="current",
			alworker="WRKR-1",
			alfrom_date="2026-01-05",
			alto_date="2026-01-06",
		)
		worker = frappe._dict(wuser="worker@example.com")
		for stored, new, blocked in (
			({"alfrom_date": date(2026, 1, 6)}, False, True),
			({"alto_date": date(2026, 1, 5), "status": "Rejected"}, False, True),
			({"alfrom_date": date(2026, 1, 7)}, False, False),
			({"docstatus": 2}, False, False),
			({"alworker": "WRKR-2"}, False, False),
			({"name": "current"}, False, False),
			({"name": "current"}, True, True),
		):
			row = {
				"name": "other",
				"alworker": "WRKR-1",
				"alfrom_date": date(2026, 1, 5),
				"alto_date": date(2026, 1, 6),
				"docstatus": 0,
				**stored,
			}
			doc["__islocal"] = new

			def get_value(doctype, filters, fieldname, *, for_update=False):
				self.assertTrue(for_update)
				self.assertEqual(doctype, "Application For Leave")
				operators = {"<=": lambda a, b: a <= b, ">=": lambda a, b: a >= b, "!=": lambda a, b: a != b}
				for field, expected in filters.items():
					value = row[field]
					if isinstance(expected, tuple):
						operator, argument = expected
						matches = operators[operator](value, argument)
					else:
						matches = value == expected
					if not matches:
						return None
				return row[fieldname]

			with (
				self.subTest(stored=stored, new=new),
				patch("frappe.get_doc", return_value=worker),
				patch.object(frappe, "db", SimpleNamespace(get_value=get_value)),
			):
				if blocked:
					with self.assertRaisesRegex(frappe.ValidationError, "already has a leave application"):
						ApplicationForLeave.before_validate(doc)
				else:
					ApplicationForLeave.before_validate(doc)

	def test_one_day_leave_uses_only_first_day_clamp(self):
		doc = LeaveDocument(
			alfrom_date="2026-01-05",
			alto_date="2026-01-05",
			alworker="WRKR-1",
			lauser="worker@example.com",
			alfrom_hours=5,
			alto_hours=1,
		)
		documents = {
			("Worker", "WRKR-1"): frappe._dict(
				wuser="worker@example.com",
				wholiday_list="RU Holidays",
				wtimesheet_template="RU Template",
			),
			("Holiday List", "RU Holidays"): frappe._dict(
				name="RU Holidays",
				from_date=date(2026, 1, 1),
				to_date=date(2026, 12, 31),
				holidays=[],
			),
			("Timesheet Template", "RU Template"): frappe._dict(
				hours_on_date=8,
				tt_working_hours_on_date="RU Short Days",
			),
			("Working Hours On Date", "RU Short Days"): frappe._dict(
				name="RU Short Days",
				hod_from_date=date(2026, 1, 1),
				hod_to_date=date(2026, 12, 31),
				hod_working_hours_table=[],
			),
		}

		with patch(
			"frappe.get_doc",
			side_effect=lambda doctype, name, **kwargs: documents[(doctype, name)],
		):
			ApplicationForLeave.validate(doc)

		self.assertEqual(doc.alfrom_hours, 5)
		self.assertEqual(doc.alto_hours, 1)
		self.assertEqual(doc.al_total_hours, 5)

	def test_requires_holiday_and_working_hours_coverage(self):
		doc = LeaveDocument(
			alfrom_date="2026-01-05",
			alto_date="2026-01-08",
			alworker="WRKR-1",
			lauser="worker@example.com",
		)
		worker = frappe._dict(
			name="WRKR-1",
			wuser="worker@example.com",
			wholiday_list="RU Holidays",
			wtimesheet_template="RU Template",
		)
		template = frappe._dict(
			name="RU Template",
			hours_on_date=8,
			tt_working_hours_on_date="RU Short Days",
		)

		for invalid_document in (
			frappe._dict(
				name="RU Holidays",
				from_date=date(2026, 1, 6),
				to_date=date(2026, 12, 31),
				holidays=[],
			),
			frappe._dict(
				name="RU Short Days",
				hod_from_date=date(2026, 1, 6),
				hod_to_date=date(2026, 12, 31),
				hod_working_hours_table=[],
			),
		):
			with self.subTest(name=invalid_document.name):
				documents = {
					("Worker", "WRKR-1"): worker,
					("Holiday List", "RU Holidays"): (
						invalid_document
						if invalid_document.name == "RU Holidays"
						else frappe._dict(
							name="RU Holidays",
							from_date=date(2026, 1, 1),
							to_date=date(2026, 12, 31),
							holidays=[],
						)
					),
					("Timesheet Template", "RU Template"): template,
					("Working Hours On Date", "RU Short Days"): invalid_document,
				}
				with (
					patch(
						"frappe.get_doc",
						side_effect=lambda doctype, name, **kwargs: documents[(doctype, name)],
					),
					self.assertRaises(frappe.ValidationError),
				):
					ApplicationForLeave.validate(doc)

	def test_approval_rolls_back_when_the_project_provider_refuses_it(self):
		from dinext_common.workflow_approval.engine import WorkflowDomainRollbackError

		def validate_approval(doc):
			raise frappe.ValidationError("<b>All projects are closed</b>")

		with (
			patch.object(frappe, "get_hooks", return_value={"validate_approval": ["test.validate_approval"]}),
			patch.object(frappe, "get_attr", return_value=validate_approval),
			self.assertRaisesRegex(WorkflowDomainRollbackError, "^All projects are closed$"),
		):
			application_for_leave.validate_workflow_vote(LeaveDocument(), "Approved")

	def test_superseded_scripts_are_excluded_from_the_fixture(self):
		app_path = Path(__file__).resolve().parents[3]
		fixture = json.loads((app_path / "fixtures/server_script.json").read_text(encoding="utf-8"))
		names = {row["name"] for row in fixture}
		self.assertTrue({"AFL_Projects", "AFL_Calculate_Hours"}.isdisjoint(names))
