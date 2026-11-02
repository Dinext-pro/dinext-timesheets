"""Position fingerprints compare reported work, using the real app hook loader."""

import json
import unittest
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from dinext_common.workflow_approval import engine


class TestApprovalFingerprint(unittest.TestCase):
	def setUp(self):
		get_hooks = frappe.get_hooks
		self.hooks = patch.object(
			frappe, "get_hooks", side_effect=lambda hook: get_hooks(hook, app_name="dinext_timesheets")
		)
		self.hooks.start()
		self.addCleanup(self.hooks.stop)
		path = (
			Path(__file__).parents[1]
			/ "dinext_timesheets/doctype/user_timesheet_position/user_timesheet_position.json"
		)
		self.fields = json.loads(path.read_text())["fields"]
		self.workflow = {
			"workflow_state_field": "workflow_state",
			"states": [{"state": "Pending Approval", "update_field": "status"}],
		}
		self.position = {
			"doctype": "User Timesheet Position",
			"user_timesheet": "_Test Parent",
			"user": "worker@example.com",
			"custom_username": "Worker",
			"user_group": "Group A",
			"project_role": "Developer",
			"period": "2026-10-42",
			"project": "_Test Project",
			"document_type": "Task",
			"document_name": "_Test Task",
			"all_hours": 8.0,
			"workflow_state": "Pending Approval",
			"status": "Pending Approval",
			"reject_reason": "",
			"custom_data": None,
			"table": [{"date": "2026-10-12", "hours": 8.0, "description": "Work", "utilized_hours": 8.0}],
		}

	def fingerprint(self, position):
		doc = SimpleNamespace(**position, meta=SimpleNamespace(fields=self.fields))
		return engine.get_content_fingerprint(doc, self.workflow)

	def test_rejection_display_and_calculated_fields_do_not_change_content(self):
		base = self.fingerprint(self.position).digest
		for field, value in (
			("reject_reason", "Please check"),
			("reject_reason", None),
			("custom_username", "Renamed Worker"),
			("all_hours", 0.0),
			("custom_data", "DEMO-ITK"),
		):
			with self.subTest(field=field, value=value):
				self.assertEqual(base, self.fingerprint({**self.position, field: value}).digest)
		changed = deepcopy(self.position)
		changed["table"][0]["utilized_hours"] = 0.0
		self.assertEqual(base, self.fingerprint(changed).digest)

	def test_all_business_context_and_detail_changes_require_new_approval(self):
		base = self.fingerprint(self.position).digest
		for field in (
			"user",
			"user_timesheet",
			"user_group",
			"period",
			"project",
			"document_type",
			"document_name",
			"project_role",
		):
			with self.subTest(field=field):
				self.assertNotEqual(base, self.fingerprint({**self.position, field: "Other"}).digest)
		for field, value in (("date", "2026-10-13"), ("hours", 7.0), ("description", "Other work")):
			with self.subTest(field=field):
				changed = deepcopy(self.position)
				changed["table"][0][field] = value
				self.assertNotEqual(base, self.fingerprint(changed).digest)

	def test_exclusions_are_scoped_to_timesheet_positions(self):
		self.assertEqual(engine._fingerprint_exclusions("Issue"), set())
		self.assertEqual(engine._fingerprint_exclusions("User Timesheet"), set())

	def test_real_utilization_recalculation_preserves_reported_work_fingerprint(self):
		with patch.object(frappe, "logger", return_value=MagicMock()):
			from dinext_timesheets.dinext_timesheets.user_timesheet.events.utilization import (
				apply_utilization_hours,
			)

		class Position(frappe._dict):
			def get_doc_before_save(self):
				return frappe._dict(status="Editing")

		doc = Position(deepcopy(self.position))
		doc.table = [frappe._dict(row) for row in doc.table]
		before = self.fingerprint(doc).digest
		project = frappe._dict(
			custom_project_utilization=[frappe._dict(pu_valid_from="2026-01-01", pu_included="Нет")]
		)
		with patch.object(frappe, "get_cached_doc", return_value=project):
			apply_utilization_hours(doc)
		self.assertEqual(doc.table[0].utilized_hours, 0)
		self.assertEqual(before, self.fingerprint(doc).digest)

	def test_old_fingerprint_is_not_accepted_or_rewritten(self):
		current = self.fingerprint(self.position)
		with patch.object(engine, "_fingerprint_exclusions", return_value=set()):
			legacy = self.fingerprint(self.position)
		self.assertNotEqual(current.digest, legacy.digest)
		from dinext_common.workflow_approval.fingerprint import find_latest_reusable_task

		criteria = {
			"approver": "approver@example.com",
			"reference_doctype": "User Timesheet Position",
			"reference_name": "_Test Position",
			"source_created_at": "2026-01-01",
			"workflow": "_Test Workflow",
			"transition_uuid": "approve",
			"transition_semantic_hash": "same",
			"content_fingerprint": current.digest,
			"content_fingerprint_version": current.version,
		}
		task = {**criteria, "status": "Completed", "content_fingerprint": legacy.digest}
		original = deepcopy(task)
		self.assertIsNone(find_latest_reusable_task([task], **criteria))
		self.assertEqual(task, original)
