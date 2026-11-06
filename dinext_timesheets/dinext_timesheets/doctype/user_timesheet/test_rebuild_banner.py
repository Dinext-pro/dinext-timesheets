# Copyright (c) 2026, Dinext and Contributors

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


class TestTimesheetRebuildRounds(unittest.TestCase):
	def test_labels_use_project_and_role_not_the_shared_user_title(self):
		from dinext_timesheets import workflow_approval

		parent = MagicMock(name="TS-1")
		parent.name = "TS-1"
		rounds = [
			{
				"round_id": "R1",
				"round_status": "Conflicted",
				"reference_name": "POS-1",
				"source_title": "the user",
				"configuration_change": {"reason": "configuration_changed"},
				"can_reset": True,
			},
			{
				"round_id": "R2",
				"round_status": "Stalled",
				"reference_name": "POS-2",
				"source_title": "the user",
				"configuration_change": None,
				"can_reset": False,
			},
		]
		positions = [
			SimpleNamespace(name="POS-1", project="Alpha", project_role="Dev"),
			SimpleNamespace(name="POS-2", project="Beta", project_role=None),
		]
		with (
			patch.object(workflow_approval.frappe, "get_doc", return_value=parent),
			patch.object(
				workflow_approval.frappe,
				"get_all",
				return_value=positions,
			) as get_positions,
			patch(
				"dinext_common.workflow_approval.api.describe_rebuild_rounds",
				return_value=rounds,
			) as describe,
		):
			result = workflow_approval.get_timesheet_rebuild_rounds("TS-1")

		parent.check_permission.assert_called_once_with("read")
		get_positions.assert_called_once_with(
			"User Timesheet Position",
			filters={"user_timesheet": "TS-1"},
			fields=["name", "project", "project_role"],
		)
		describe.assert_called_once_with("User Timesheet Position", ["POS-1", "POS-2"])
		self.assertEqual(result[0]["label"], "Alpha · Dev")
		self.assertEqual(result[1]["label"], "Beta")
		self.assertEqual(result[0]["configuration_change"], rounds[0]["configuration_change"])
		self.assertTrue(result[0]["can_reset"])
		self.assertFalse(result[1]["can_reset"])
		self.assertNotIn("source_title", result[0])
		self.assertNotIn("the user", str(result))
