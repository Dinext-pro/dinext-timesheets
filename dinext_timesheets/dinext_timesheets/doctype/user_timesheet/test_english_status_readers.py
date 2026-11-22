# Copyright (c) 2026, Dinext and Contributors
# See license.txt

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from dinext_timesheets.dinext_timesheets.user_timesheet.events.hours import (
	calculate_utp_all_hours,
)
from dinext_timesheets.dinext_timesheets.user_timesheet.events.journal import (
	maybe_create_or_cancel_journal_entries,
)
from dinext_timesheets.timesheet_status import APPROVED_POSITION_STATUSES


class TestEnglishStatusReaders(FrappeTestCase):
	def test_fact_queries_include_approved_and_legacy_status(self):
		from dinext_project_tasks_gantt import burndown
		from project_workload_assignment import approval_statuses
		from project_workload_assignment.project_workload_assignment.project_workload.utilization import utp_actual
		from project_workload_assignment.project_workload_assignment.work_efforts import (
			consolidated_data,
			work_efforts_progress,
		)

		for module, condition, count in (
			(work_efforts_progress, "UTP.status.isin(APPROVED_STATUSES)", 1),
			(consolidated_data, "UTP.status.isin(APPROVED_STATUSES)", 1),
			(utp_actual, "utp.status.isin(APPROVED_STATUSES)", 2),
			(burndown, "utp.status.isin(APPROVED_POSITION_STATUSES)", 2),
		):
			with self.subTest(module=module.__name__):
				self.assertEqual(Path(module.__file__).read_text().count(condition), count)
		self.assertEqual(approval_statuses.APPROVED_STATUSES, APPROVED_POSITION_STATUSES)
		self.assertEqual(burndown.APPROVED_POSITION_STATUSES, APPROVED_POSITION_STATUSES)

		utp = frappe.qb.DocType("User Timesheet Position")
		sql = (
			frappe.qb.from_(utp)
			.select(utp.name)
			.where(utp.status.isin(APPROVED_POSITION_STATUSES))
			.get_sql()
		)
		self.assertIn("Approved", sql)
		self.assertIn("Согласовано", sql)

	def test_approved_timesheet_creates_journal_entries(self):
		doc = SimpleNamespace(
			name="UT-1",
			ut_status="Approved",
			get_doc_before_save=lambda: SimpleNamespace(ut_status="Rework"),
		)
		with patch(
			"dinext_timesheets.dinext_timesheets.user_timesheet.events.journal.call_whitelisted_function"
		) as call:
			maybe_create_or_cancel_journal_entries(doc)
		call.assert_called_once_with(
			"create_journal_entries_for_approved_timesheet",
			doc=doc,
		)

	def test_editing_position_sums_hours(self):
		doc = SimpleNamespace(
			status="Editing",
			table=[SimpleNamespace(hours=2), SimpleNamespace(hours=3)],
			all_hours=0,
		)
		calculate_utp_all_hours(doc)
		self.assertEqual(doc.all_hours, 5)

		approved = SimpleNamespace(
			status="Approved",
			table=[SimpleNamespace(hours=9)],
			all_hours=1,
		)
		calculate_utp_all_hours(approved)
		self.assertEqual(approved.all_hours, 1)
