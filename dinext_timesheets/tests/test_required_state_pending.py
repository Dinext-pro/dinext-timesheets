"""Timesheet position aggregation consumes the common mandatory-target rule."""

from unittest.mock import patch

import frappe
from dinext_common.tests.test_required_state_pending import PendingFixture
from frappe.tests.utils import FrappeTestCase

from dinext_timesheets import workflow_approval


class TestTimesheetRequiredPending(PendingFixture, FrappeTestCase):
	def setUp(self):
		super().setUp()
		self.workflow = self.make_workflow(doctype="User Timesheet Position")
		self.parent = frappe.get_doc(
			{
				"doctype": "User Timesheet",
				"name": "_Test Pending UT " + frappe.generate_hash(length=10),
				"timesheet_from": "Administrator",
			}
		)
		self.parent.db_insert()
		self.positions = []
		for _ in range(2):
			position = frappe.get_doc(
				{
					"doctype": "User Timesheet Position",
					"name": "_Test Pending UTP " + frappe.generate_hash(length=10),
					"user_timesheet": self.parent.name,
				}
			)
			position.db_insert()
			self.positions.append(position)

	def test_required_targets_are_aggregated_per_position(self):
		first, second = self.positions
		self.task("shared@example.com", ["Required"], source=first)
		self.task("shared@example.com", ["Optional"], source=second)
		self.task("second@example.com", ["Required"], source=second)
		self.task("optional@example.com", ["Optional"], source=first)
		rows = workflow_approval.pending_approvers("User Timesheet", self.parent.name)
		self.assertEqual(
			{(row["approver"], row["reference_name"]) for row in rows},
			{("shared@example.com", first.name), ("second@example.com", second.name)},
		)
		self.assertTrue(
			all(
				set(row) == {"approver", "approval_round_id", "workflow_state", "reference_name"}
				for row in rows
			)
		)

	def test_optional_only_positions_clear_the_list(self):
		for source in self.positions:
			self.task("optional@example.com", ["Optional"], source=source)
		self.assertEqual(workflow_approval.pending_approvers("User Timesheet", self.parent.name), [])

	def test_other_doctypes_are_left_to_the_generic_api(self):
		self.assertIsNone(workflow_approval.pending_approvers("ToDo", self.source.name))
