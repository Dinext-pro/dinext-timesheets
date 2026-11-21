"""Regression coverage for the legacy position status mirror."""

from unittest import TestCase
from unittest.mock import patch

import frappe

from dinext_timesheets.dinext_timesheets.user_timesheet.events import workflow_tasks


class TestWorkflowTasksBridge(TestCase):
	def setUp(self):
		self.position = frappe._dict(workflow_state="Editing", status="Approved")
		self.legacy_schema = self.enterContext(
			patch.object(workflow_tasks, "has_legacy_position_status", return_value=True)
		)
		self.scenarios = self.enterContext(
			patch("dinext_timesheets.workflow_scenario_actions.uses_local_scenarios", return_value=False)
		)

	def test_legacy_schema_keeps_status_mirror_in_sync(self):
		workflow_tasks.sync_status_from_workflow_state(self.position)
		self.assertEqual(self.position.status, "Editing")

	def test_native_schema_preserves_its_status(self):
		self.legacy_schema.return_value = False
		workflow_tasks.sync_status_from_workflow_state(self.position)
		self.assertEqual(self.position.status, "Approved")

	def test_scenario_on_status_preserves_native_value_with_legacy_schema(self):
		self.scenarios.return_value = True
		with patch("dinext_common.workflow_approval.scenarios.service.get_context", return_value={"state_field": "status"}):
			workflow_tasks.sync_status_from_workflow_state(self.position)
		self.assertEqual(self.position.status, "Approved")
