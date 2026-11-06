"""Aggregate actions retain destinations without changing their availability."""

from unittest.mock import MagicMock, patch

from frappe.tests.utils import FrappeTestCase

from dinext_timesheets.workflow_approval import get_timesheet_approval_actions


def task(name, position, *transitions):
	return {
		"name": name,
		"reference_doctype": "User Timesheet Position",
		"reference_name": position,
		"available_transitions": [
			{"action": action, "next_state": state, "comment_is_required": required}
			for action, state, required in transitions
		],
	}


class TestTimesheetWorkflowTransitionStyles(FrappeTestCase):
	def actions(self, tasks):
		parent = MagicMock(name="timesheet")
		parent.name = "Style timesheet"
		with (
			patch("dinext_timesheets.workflow_approval.frappe.get_doc", return_value=parent),
			patch("dinext_timesheets.workflow_approval.frappe.get_all", return_value=["p1", "p2"]),
			patch("dinext_common.workflow_approval.api.get_my_queue", return_value=tasks),
		):
			result = get_timesheet_approval_actions(parent.name)
		parent.check_permission.assert_called_once_with("read")
		return result

	def test_destinations_are_retained_for_each_common_action(self):
		result = self.actions(
			[
				task("t1", "p1", ("Approve", "Approved", False), ("Reject", "Rejected", True)),
				task("t2", "p2", ("Approve", "Approved", False)),
				task("other", "other-position", ("Approve", "Rejected", False)),
			]
		)
		self.assertEqual(result["tasks"], ["t1", "t2"])
		self.assertEqual(result["position_count"], 2)
		self.assertEqual(
			result["actions"],
			[
				{
					"action": "Approve",
					"comment_is_required": False,
					"positions": [{"next_state": "Approved"}, {"next_state": "Approved"}],
				}
			],
		)

	def test_conflicting_destinations_are_preserved_for_neutral_rendering(self):
		result = self.actions(
			[
				task("t1", "p1", ("Review", "Approved", False)),
				task("t2", "p2", ("Review", "Needs review", True)),
			]
		)
		self.assertEqual(
			result["actions"],
			[
				{
					"action": "Review",
					"comment_is_required": True,
					"positions": [{"next_state": "Approved"}, {"next_state": "Needs review"}],
				}
			],
		)

	def test_no_tasks_produce_no_actions(self):
		self.assertEqual(self.actions([]), {"tasks": [], "position_count": 0, "actions": []})
