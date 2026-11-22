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
		apps = Path(frappe.get_app_path("dinext_timesheets")).parents[1]
		progress = (
			apps
			/ "project_workload_assignment"
			/ "project_workload_assignment"
			/ "project_workload_assignment"
			/ "work_efforts"
			/ "work_efforts_progress.py"
		).read_text()
		burndown = (
			apps / "dinext_project_tasks_gantt" / "dinext_project_tasks_gantt" / "burndown.py"
		).read_text()
		consolidated = (
			apps
			/ "project_workload_assignment"
			/ "project_workload_assignment"
			/ "project_workload_assignment"
			/ "work_efforts"
			/ "consolidated_data.py"
		).read_text()
		utilization = (
			apps
			/ "project_workload_assignment"
			/ "project_workload_assignment"
			/ "project_workload_assignment"
			/ "project_workload"
			/ "utilization"
			/ "utp_actual.py"
		).read_text()
		self.assertIn("UTP.status.isin(APPROVED_POSITION_STATUSES)", progress)
		self.assertIn("UTP.status.isin(APPROVED_POSITION_STATUSES)", consolidated)
		self.assertEqual(utilization.count("utp.status.isin(APPROVED_POSITION_STATUSES)"), 2)
		self.assertIn("utp.status.isin(APPROVED_POSITION_STATUSES)", burndown)

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
