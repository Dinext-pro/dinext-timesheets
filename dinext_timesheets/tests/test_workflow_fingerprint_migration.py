"""One-time migration preserves parent configuration, source data and digest."""

from unittest.mock import patch

import frappe
from dinext_common.workflow_approval.engine import get_content_fingerprint
from frappe.tests.utils import FrappeTestCase

from dinext_timesheets.patches.v1_0.migrate_fingerprint_exclusions import DEFAULT_EXCLUSIONS, execute


class TestWorkflowFingerprintMigration(FrappeTestCase):
	def setUp(self):
		super().setUp()
		self.previous = frappe.conf.get("enable_parallel_workflow_approval")
		frappe.conf.enable_parallel_workflow_approval = False
		self.addCleanup(lambda: setattr(frappe.conf, "enable_parallel_workflow_approval", self.previous))
		self.workflow = frappe.get_doc(
			{
				"doctype": "Workflow",
				"workflow_name": "_Test exclusions " + frappe.generate_hash(length=8),
				"document_type": "User Timesheet Position",
				"workflow_state_field": "workflow_state",
				"is_active": 0,
				"states": [{"state": "Editing", "doc_status": "0", "allow_edit": "System Manager"}],
			}
		).insert(ignore_permissions=True)

	def test_migration_is_idempotent_and_never_saves_workflow(self):
		self.workflow.append("custom_fingerprint_excluded_fields", {"field_path": "project"})
		self.workflow.update_child_table("custom_fingerprint_excluded_fields")
		before = self.workflow.modified
		with patch.object(type(self.workflow), "save", side_effect=AssertionError("Workflow.save called")):
			execute()
			execute()
		self.workflow.reload()
		paths = [row.field_path for row in self.workflow.custom_fingerprint_excluded_fields]
		self.assertEqual(set(paths), {*DEFAULT_EXCLUSIONS, "project"})
		self.assertEqual(len(paths), len(set(paths)))
		self.assertEqual(frappe.utils.get_datetime(before), self.workflow.modified)

	def test_moving_defaults_preserves_digest(self):
		doc = frappe.get_doc(
			{
				"doctype": "User Timesheet Position",
				"user": "Administrator",
				"all_hours": 8,
				"custom_username": "Owner",
				"custom_data": "tag",
				"reject_reason": "Rejected",
				"table": [{"date": "2039-01-03", "hours": 8, "description": "Work", "utilized_hours": 8}],
			}
		)
		with patch(
			"dinext_common.workflow_approval.engine.frappe.get_hooks",
			return_value=[{"User Timesheet Position": list(DEFAULT_EXCLUSIONS)}],
		):
			before = get_content_fingerprint(doc, self.workflow).digest
		execute()
		self.workflow.reload()
		with patch("dinext_common.workflow_approval.engine.frappe.get_hooks", return_value=[]):
			after = get_content_fingerprint(doc, self.workflow).digest
		self.assertEqual(before, after)

	def test_patch_log_prevents_restoring_a_removed_setting(self):
		execute()
		self.workflow.reload()
		self.workflow.set(
			"custom_fingerprint_excluded_fields",
			[
				{"field_path": row.field_path}
				for row in self.workflow.custom_fingerprint_excluded_fields
				if row.field_path != "reject_reason"
			],
		)
		self.workflow.update_child_table("custom_fingerprint_excluded_fields")
		module = "dinext_timesheets.patches.v1_0.migrate_fingerprint_exclusions"
		if not frappe.db.exists("Patch Log", {"patch": module, "skipped": 0}):
			frappe.get_doc({"doctype": "Patch Log", "patch": module}).insert(ignore_permissions=True)
		from frappe.modules.patch_handler import run_single

		with patch(module + ".execute", side_effect=AssertionError("Completed patch reran")):
			self.assertTrue(run_single(module))
		self.workflow.reload()
		self.assertNotIn(
			"reject_reason", [row.field_path for row in self.workflow.custom_fingerprint_excluded_fields]
		)

	def test_packaged_workflow_supplies_defaults_on_first_install(self):
		import json
		from pathlib import Path

		from frappe.modules.import_file import import_doc

		fixtures = json.loads(
			Path(frappe.get_app_path("dinext_timesheets", "fixtures", "workflow.json")).read_text()
		)
		fixture = next(doc for doc in fixtures if doc["document_type"] == "User Timesheet Position")
		fixture["name"] = fixture["workflow_name"] = "_Test packaged snapshot " + frappe.generate_hash(
			length=8
		)
		fixture["is_active"] = 0
		previous = {key: frappe.flags.get(key) for key in ("in_fixtures", "in_import")}
		try:
			frappe.flags.in_fixtures = True
			import_doc(fixture)
			workflow = frappe.get_doc("Workflow", fixture["name"])
			self.assertEqual(
				[row.field_path for row in workflow.custom_fingerprint_excluded_fields],
				list(DEFAULT_EXCLUSIONS),
			)
		finally:
			frappe.flags.update(previous)
