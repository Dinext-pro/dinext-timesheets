"""Exercise position comment forwarding through the installed document hooks."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase


class TestWorkflowComments(FrappeTestCase):
	def setUp(self):
		super().setUp()
		self.parent = frappe.get_doc({
			"name": "_Test WF Comments " + frappe.generate_hash(length=10),
			"doctype": "User Timesheet",
			"timesheet_from": "Administrator",
			"timesheet_from_name": "test-workflow-comments",
			"ts_valid_from": "2039-01-03",
			"ts_valid_for": "2039-01-09",
			"ut_status": "Draft",
		})
		# Calendar and round creation are unrelated to the Comment lifecycle under test.
		self.parent.db_insert()
		self.position = frappe.get_doc({
			"name": "_Test WF Position " + frappe.generate_hash(length=10),
			"doctype": "User Timesheet Position",
			"user_timesheet": self.parent.name,
			"user": "Administrator",
			"workflow_state": "Editing",
			"status": "Editing",
		})
		self.position.db_insert()

	def copies(self, content):
		return frappe.get_all("Comment", filters={
			"reference_doctype": "User Timesheet",
			"reference_name": self.parent.name,
			"content": f"{self.position.name}: {content}",
		}, fields=["comment_type", "comment_email", "comment_by", "content"])

	def test_one_workflow_event_creates_one_parent_entry(self):
		for enabled in (True, False):
			with self.subTest(parallel_engine=enabled), patch.dict(
				frappe.conf, {"enable_parallel_workflow_approval": enabled}
			):
				content = f"Workflow event with engine {enabled}"
				source = self.position.add_comment("Workflow", content)
				copies = self.copies(content)
				self.assertEqual(len(copies), 1)
				self.assertEqual(copies[0].comment_type, "Workflow")
				self.assertEqual(copies[0].comment_email, source.comment_email)
				self.assertEqual(copies[0].comment_by, source.comment_by)

	def test_distinct_identical_events_are_not_deduplicated(self):
		content = "Returned to editing"
		self.position.add_comment("Workflow", content)
		self.position.add_comment("Workflow", content)
		self.assertEqual(len(self.copies(content)), 2)

	def test_ordinary_position_comments_still_reach_the_parent(self):
		content = "Please check the hours"
		self.position.add_comment("Comment", content)
		copies = self.copies(content)
		self.assertEqual(len(copies), 1)
		self.assertEqual(copies[0].comment_type, "Comment")
