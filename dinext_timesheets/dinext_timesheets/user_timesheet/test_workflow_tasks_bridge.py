"""Regression coverage for UTP single-engine rollout selection."""

from unittest.mock import Mock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from dinext_timesheets.dinext_timesheets.user_timesheet.events import workflow_tasks as bridge


class TestWorkflowTasksBridge(FrappeTestCase):
	def setUp(self):
		super().setUp()
		self.legacy_schema = self.enterContext(patch.object(bridge, "has_legacy_position_status", return_value=True))
		self.enterContext(patch("dinext_timesheets.workflow_scenario_actions.uses_local_scenarios", return_value=False))

	def position(self):
		return frappe.get_doc({
			"doctype": "User Timesheet Position",
			"name": "TEST-UTP-BRIDGE",
			"workflow_state": "Editing",
			"status": "stale",
		})

	def test_parallel_before_save_syncs_status_without_legacy_processor(self):
		doc = self.position()
		with patch.object(bridge, "is_engine_enabled", return_value=True), patch.object(bridge, "call_whitelisted_function") as legacy:
			bridge.process_workflow_tasks_before_save(doc)
		self.assertEqual(doc.status, "Editing")
		legacy.assert_not_called()

	def test_parallel_after_save_does_not_invoke_legacy_processor(self):
		with patch.object(bridge, "is_engine_enabled", return_value=True), patch.object(bridge, "call_whitelisted_function") as legacy:
			bridge.process_workflow_tasks_after_save(self.position())
		legacy.assert_not_called()

	def test_native_status_is_kept_when_a_legacy_value_is_present_in_memory(self):
		self.legacy_schema.return_value = False
		doc = self.position()
		doc.status = "Approved"
		with patch.object(bridge, "is_engine_enabled", return_value=True):
			bridge.process_workflow_tasks_before_save(doc)
		self.assertEqual(doc.status, "Approved")

	def test_parallel_trash_leaves_task_audit_for_archive_lifecycle(self):
		with patch.object(bridge, "is_engine_enabled", return_value=True), patch.object(bridge.frappe, "get_all") as query, patch.object(bridge.frappe, "get_doc") as load:
			bridge.delete_linked_workflow_tasks(frappe._dict(name="TEST-UTP-BRIDGE"))
		query.assert_not_called()
		load.assert_not_called()

	def test_legacy_before_save_preserves_dict_scalar_updates_and_identity(self):
		doc = self.position()
		returned = {"workflow_state": "Подтверждено", "name": "WRONG", "doctype": "WRONG", "_private": "ignored", "table": ["ignored"], "all_hours": 2}
		with patch.object(bridge, "is_engine_enabled", return_value=False), patch.object(bridge, "call_whitelisted_function", return_value={"doc": returned}) as legacy:
			bridge.process_workflow_tasks_before_save(doc)
		legacy.assert_called_once_with("Workflow_Task_Processing", doc=doc)
		self.assertEqual(doc.name, "TEST-UTP-BRIDGE")
		self.assertEqual(doc.doctype, "User Timesheet Position")
		self.assertEqual(doc.status, "Подтверждено")
		self.assertEqual(doc.all_hours, 2)
		self.assertEqual(doc.table, [])
		self.assertIsNone(doc.get("_private"))

	def test_legacy_empty_result_still_syncs_status(self):
		doc = self.position()
		with patch.object(bridge, "is_engine_enabled", return_value=False), patch.object(bridge, "call_whitelisted_function", return_value=None):
			bridge.process_workflow_tasks_before_save(doc)
		self.assertEqual(doc.status, "Editing")

	def test_legacy_document_result_skips_identity_and_child_tables(self):
		doc = self.position()
		source = frappe.get_doc({"doctype": "User Timesheet Position", "name": "WRONG", "owner": "WRONG", "workflow_state": "Подтверждено", "all_hours": 3, "table": [{"date": "2026-10-09", "hours": 3}]})
		legacy_fields = {**source.as_dict(), "workflow_state": "Подтверждено"}
		with (
			patch.object(source, "as_dict", return_value=legacy_fields),
			patch.object(bridge, "is_engine_enabled", return_value=False),
			patch.object(bridge, "call_whitelisted_function", return_value={"doc": source}),
		):
			bridge.process_workflow_tasks_before_save(doc)
		self.assertEqual(doc.name, "TEST-UTP-BRIDGE")
		self.assertEqual(doc.status, "Подтверждено")
		self.assertEqual(doc.all_hours, 3)
		self.assertEqual(doc.table, [])
		self.assertNotEqual(doc.owner, "WRONG")

	def test_legacy_after_save_retains_processor(self):
		doc = self.position()
		with patch.object(bridge, "is_engine_enabled", return_value=False), patch.object(bridge, "call_whitelisted_function") as legacy:
			bridge.process_workflow_tasks_after_save(doc)
		legacy.assert_called_once_with("Workflow_Task_Processing_After_Save", doc=doc)

	def test_legacy_trash_retains_linked_task_deletion(self):
		doc = frappe._dict(name="TEST-UTP-BRIDGE")
		task = Mock()
		with patch.object(bridge, "is_engine_enabled", return_value=False), patch.object(bridge.frappe, "get_all", return_value=[frappe._dict(name="TEST-WT")]) as query, patch.object(bridge.frappe, "get_doc", return_value=task) as load:
			bridge.delete_linked_workflow_tasks(doc)
		query.assert_called_once_with("Workflow Task", filters={"wt_docname": doc.name}, ignore_permissions=True)
		load.assert_called_once_with("Workflow Task", "TEST-WT")
		task.delete.assert_called_once_with(ignore_permissions=True)
