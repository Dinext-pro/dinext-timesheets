"""Timesheet position batches retain independent outcomes and replay their reports."""

import json
import unittest
from unittest.mock import patch

import frappe
from frappe.model.document import Document

from dinext_timesheets.tests import test_workflow_scenario_timesheet_integration as scenarios
from dinext_common.workflow_approval import api, engine, request_receipts
from dinext_timesheets import workflow_approval, workflow_scenario_actions


class TestWorkflowPositionBatchFailures(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		scenarios.TestWorkflowScenarioTimesheetIntegration.setUpClass()

	def setUp(self):
		self.fixture = scenarios.TestWorkflowScenarioTimesheetIntegration()
		self.addCleanup(self.fixture.doCleanups)
		self.fixture.setUp()
		self.empty_role = self.fixture.marker + " Empty Role"
		frappe.get_doc({"doctype": "Role", "role_name": self.empty_role}).insert(ignore_permissions=True)

	def _block_successor(self, index, state):
		workflow = self.fixture.workflows[index].reload()
		for transition in workflow.transitions:
			if transition.state == state:
				transition.allowed = self.empty_role
		workflow.save(ignore_permissions=True)

	def _run_batch(self, action, request_id):
		parent = self.fixture.parent
		targets = next(
			row["targets"]
			for row in workflow_approval.get_timesheet_position_actions(parent.name)["actions"]
			if row["action"] == action
		)
		args = {
			"timesheet_name": parent.name,
			"action": action,
			"comment": "Review the synthetic positions",
			"request_id": request_id,
			"targets": targets,
			"track_progress": True,
		}
		events = []
		with patch.object(frappe, "publish_realtime", side_effect=lambda event, data=None, **kwargs: (
			events.append((data or kwargs["message"])["count"]) if event == "dinext_workflow_progress" else None
		)):
			result = workflow_approval.apply_timesheet_position_action(**args)
		self.assertEqual(events, list(range(1, result["total"] + 1)))
		self.assertEqual(workflow_approval.apply_timesheet_position_action(**args), result)
		return result

	def _assert_missing_cohort(self, failure, blocked_index, state):
		fixture = self.fixture
		blocked = fixture.positions[blocked_index]
		details = failure["workflow_error"]
		self.assertEqual(failure["name"], blocked.name)
		self.assertEqual(failure["error_type"], "NoEligibleApproversError")
		self.assertEqual(details["code"], "no_eligible_approvers")
		self.assertEqual((details["doctype"], details["name"]), (scenarios.POSITION, blocked.name))
		self.assertEqual((details["workflow"], details["state"]), (fixture.workflows[blocked_index].name, state))
		self.assertEqual([transition["role"] for transition in details["transitions"]], [self.empty_role])
		for token in (details["workflow"], state, self.empty_role):
			self.assertIn(token, failure["error"])

	def test_first_failed_position_leaves_prior_vote_and_rolls_up_later_success(self):
		fixture = self.fixture
		self._block_successor(0, "Rejected")
		first, last = fixture.positions
		prior_vote = fixture._task_for(first, fixture.other)
		task = fixture._task_for(first, fixture.reviewer)
		frappe.set_user(fixture.other)
		self.assertFalse(fixture._reject(first, prior_vote, "A")["transitioned"])
		comment_count = fixture._workflow_comments(first)
		frappe.set_user(fixture.reviewer)

		result = self._run_batch(fixture.action, fixture.marker)

		self.assertEqual((result["processed"], result["total"]), (2, 2))
		self.assertEqual([row["reference_name"] for row in result["results"]], [last.name])
		self.assertEqual(len(result["failed"]), 1)
		self._assert_missing_cohort(result["failed"][0], 0, "Rejected")
		self.assertEqual(result["messages"], [])
		self.assertEqual(fixture._state_of_task(prior_vote), ("Completed", "Open"))
		self.assertEqual(fixture._state_of_task(task), ("Working", "Open"))
		self.assertEqual(fixture._workflow_comments(first), comment_count)
		self.assertEqual(first.reload().status, "Pending Approval")
		self.assertEqual(last.reload().status, "Rejected")
		self.assertEqual(fixture.parent.reload().ut_status, "Rejected")

	def test_last_failed_position_retains_earlier_vote_below_quorum(self):
		fixture = self.fixture
		self._block_successor(1, "Rejected")
		first, last = fixture.positions
		task = fixture._task_for(first, fixture.reviewer)
		blocked_task = fixture._task_for(last, fixture.reviewer)
		comment_count = fixture._workflow_comments(last)
		frappe.set_user(fixture.reviewer)

		result = self._run_batch(fixture.action, fixture.marker)

		self.assertEqual((result["processed"], result["total"]), (2, 2))
		self.assertEqual([(row["reference_name"], row["transitioned"]) for row in result["results"]],
			[(first.name, False)])
		self.assertEqual(len(result["failed"]), 1)
		self._assert_missing_cohort(result["failed"][0], 1, "Rejected")
		self.assertEqual(result["messages"], [])
		self.assertEqual(fixture._state_of_task(task), ("Completed", "Open"))
		self.assertEqual(fixture._state_of_task(blocked_task), ("Working", "Open"))
		self.assertEqual(fixture._workflow_comments(last), comment_count)
		self.assertEqual(last.reload().status, "Pending Approval")
		self.assertEqual(fixture.parent.reload().ut_status, "Pending Approval")

	def test_mandatory_rework_reports_sibling_and_rolls_back_trigger(self):
		fixture = self.fixture
		trigger, sibling = fixture.positions
		action = fixture.marker + " Edit"
		sibling_action = fixture.marker + " Sibling Edit"
		fixture._master("Workflow State", "Editing", {"workflow_state_name": "Editing"})
		for label in (action, sibling_action):
			fixture._master("Workflow Action Master", label, {"workflow_action_name": label})
		fixture._add_edit_transition(0, "A", action)
		fixture._add_edit_transition(1, "B", sibling_action)
		self._block_successor(1, "Editing")
		fixture._set_rules(("Editing", "Rework", "Any", 0, 1))
		prior_vote = fixture._task_for(trigger, fixture.other)
		trigger_task = fixture._task_for(trigger, fixture.reviewer)
		sibling_task = fixture._task_for(sibling, fixture.reviewer)
		frappe.set_user(fixture.other)
		api.vote(prior_vote, transition_uuid=fixture.marker + "-A")
		frappe.set_user(fixture.reviewer)
		comment_count = fixture._workflow_comments(trigger, sibling)

		result = workflow_approval.apply_timesheet_position_action(
			fixture.parent.name, action, request_id=fixture.marker
		)

		self.assertEqual((result["processed"], result["total"]), (1, 1))
		self.assertEqual(result["results"], [])
		self.assertEqual(len(result["failed"]), 1)
		self._assert_missing_cohort(result["failed"][0], 1, "Editing")
		self.assertIn("rolled back", result["failed"][0]["error"])
		self.assertEqual(fixture._state_of_task(prior_vote), ("Completed", "Open"))
		self.assertEqual(fixture._state_of_task(trigger_task), ("Working", "Open"))
		self.assertEqual(fixture._state_of_task(sibling_task), ("Working", "Open"))
		self.assertEqual(fixture._workflow_comments(trigger, sibling), comment_count)
		self.assertEqual(trigger.reload().status, "Pending Approval")
		self.assertEqual(sibling.reload().status, "Pending Approval")
		self.assertEqual(fixture.parent.reload().ut_status, "Pending Approval")
		self.assertEqual(workflow_approval.apply_timesheet_position_action(
			fixture.parent.name, action, request_id=fixture.marker
		), result)

	def test_failed_rework_rolls_back_a_below_quorum_vote_from_the_same_batch(self):
		fixture = self.fixture
		sibling, trigger = fixture.positions
		sibling_action = fixture.marker + " Sibling Edit"
		fixture._master("Workflow State", "Editing", {"workflow_state_name": "Editing"})
		fixture._master("Workflow Action Master", sibling_action, {"workflow_action_name": sibling_action})
		fixture._add_edit_transition(0, "A", sibling_action)
		self._block_successor(0, "Editing")

		workflow = fixture.workflows[1].reload()
		transition = next(row for row in workflow.transitions if row.action == fixture.action)
		transition.action = sibling_action
		workflow.save(ignore_permissions=True)
		fixture._add_edit_transition(1, "B", fixture.action)
		stale_task = fixture._task_for(trigger, fixture.reviewer)
		engine._cancel_round(frappe.db.get_value("Workflow Task", stale_task, "approval_round_id"), fixture.marker)
		engine.reconcile_source(trigger)
		fixture._set_rules(("Editing", "Rework", "Any", 0, 1))
		comments = fixture._workflow_comments(sibling)
		accepted_task = fixture._task_for(sibling, fixture.reviewer)
		trigger_task = fixture._task_for(trigger, fixture.reviewer)
		frappe.set_user(fixture.reviewer)

		result = self._run_batch(fixture.action, fixture.marker)

		self.assertEqual((result["processed"], result["total"]), (2, 2))
		self.assertEqual(result["results"], [], result)
		self.assertEqual(len(result["failed"]), 1)
		self._assert_missing_cohort(result["failed"][0], 0, "Editing")
		self.assertEqual(fixture._state_of_task(accepted_task), ("Working", "Open"))
		self.assertEqual(fixture._workflow_comments(sibling), comments)
		self.assertEqual(fixture._state_of_task(trigger_task), ("Working", "Open"))
		self.assertEqual(trigger.reload().status, "Pending Approval")
		self.assertEqual(fixture.parent.reload().ut_status, "Pending Approval")

	def test_rolled_back_realtime_events_do_not_displace_later_events(self):
		from frappe.realtime import clear_realtime_log, flush_realtime_log

		from dinext_timesheets.workflow_scenario_actions import TimesheetTransitionError, atomic_timesheet_transition

		original_log = getattr(frappe.local, "_realtime_log", None)
		callbacks = [(manager, tuple(manager._functions)) for manager in (frappe.db.after_commit, frappe.db.after_rollback)]

		def restore():
			clear_realtime_log()
			if original_log is not None:
				frappe.local._realtime_log = original_log
			for manager, previous in callbacks:
				manager.reset()
				for callback in previous:
					manager.add(callback)

		self.addCleanup(restore)
		for existing_log in (False, True):
			with self.subTest(existing_log=existing_log):
				clear_realtime_log()
				for manager, _previous in callbacks:
					manager.reset()
				if existing_log:
					frappe.publish_realtime("timesheet_before", room="synthetic", after_commit=True)
				with self.assertRaises(TimesheetTransitionError), atomic_timesheet_transition():
					frappe.publish_realtime("timesheet_reverted", room="synthetic", after_commit=True)
					raise TimesheetTransitionError("Rollback for this test")

				frappe.publish_realtime("timesheet_after", room="synthetic", after_commit=True)
				self.assertEqual(tuple(frappe.db.after_commit._functions), (flush_realtime_log,))
				with patch("frappe.realtime.emit_via_redis") as emit:
					frappe.db.after_commit.run()
				expected = ["timesheet_before", "timesheet_after"] if existing_log else ["timesheet_after"]
				self.assertEqual([call.args[0] for call in emit.call_args_list], expected)

	def _start_rejected_cascade(self):
		fixture = self.fixture
		sibling, trigger = fixture.positions
		self._block_successor(0, "Rejected")
		fixture._set_rules(("Rejected", "Rejected", "Any", 0, 1))
		frappe.set_user(fixture.reviewer)
		sibling_vote = fixture._task_for(sibling, fixture.reviewer)
		self.assertFalse(fixture._reject(sibling, sibling_vote, "A")["transitioned"])
		return sibling, trigger

	def _deny_sibling_read(self, sibling):
		original = Document.has_permission

		def has_permission(doc, permtype="read", *args, **kwargs):
			if doc.doctype == sibling.doctype and doc.name == sibling.name and permtype == "read":
				return False
			return original(doc, permtype, *args, **kwargs)

		return patch.object(Document, "has_permission", has_permission)

	def test_mandatory_cascade_reports_related_position_and_scopes_replay(self):
		sibling, trigger = self._start_rejected_cascade()
		fixture = self.fixture
		args = {"timesheet_name": fixture.parent.name, "action": fixture.action,
			"comment": "Review the synthetic positions", "request_id": fixture.marker}

		result = workflow_approval.apply_timesheet_position_action(**args)

		self.assertEqual(result["results"], [])
		self.assertEqual(len(result["failed"]), 1)
		self._assert_missing_cohort(result["failed"][0], 0, "Rejected")
		self.assertEqual(result["messages"], [])
		self.assertEqual(sibling.reload().status, "Pending Approval")
		self.assertEqual(trigger.reload().status, "Pending Approval")
		self.assertEqual(fixture.parent.reload().ut_status, "Pending Approval")
		self.assertEqual(workflow_approval.apply_timesheet_position_action(**args), result)
		cause = engine.NoEligibleApproversError(result["failed"][0]["workflow_error"])
		with self._deny_sibling_read(sibling):
			with self.assertRaises(frappe.PermissionError):
				workflow_approval.apply_timesheet_position_action(**args)
			failure = workflow_scenario_actions._cascade_failure(sibling, cause)
			self.assertIsNone(failure["name"])
			self.assertIsNone(failure["workflow_error"])
			self.assertNotIn(sibling.name, failure["error"])

	def test_mandatory_cascade_hides_unreadable_related_position(self):
		sibling, trigger = self._start_rejected_cascade()
		fixture = self.fixture
		args = {"timesheet_name": fixture.parent.name, "action": fixture.action,
			"comment": "Review the synthetic positions", "request_id": fixture.marker}
		with self._deny_sibling_read(sibling):
			result = workflow_approval.apply_timesheet_position_action(**args)
			self.assertEqual(workflow_approval.apply_timesheet_position_action(**args), result)

		self.assertEqual(result["results"], [])
		self.assertEqual(len(result["failed"]), 1)
		failure = result["failed"][0]
		self.assertIsNone(failure["name"])
		self.assertIsNone(failure["workflow_error"])
		self.assertIn("rolled back", failure["error"])
		self.assertEqual(trigger.reload().status, "Pending Approval")
		self.assertNotIn(sibling.name, json.dumps(result))
		self.assertNotIn(self.empty_role, json.dumps(result))
		receipt = request_receipts.get(request_receipts.request_key("Timesheet", fixture.marker))
		self.assertNotIn(sibling.name, receipt.targets)

	def test_pending_cascade_validation_leaves_parent_and_positions_unchanged(self):
		fixture = self.fixture
		sibling, trigger = fixture.positions
		field = fixture.workflows[0].workflow_state_field
		frappe.db.set_value(scenarios.POSITION, sibling.name, {"status": "Rejected", field: "Rejected"})
		frappe.db.set_value("User Timesheet", fixture.parent.name, "ut_status", "Draft")
		fixture._set_rules(("Pending Approval", "Pending Approval", "Any", 0, 1))
		comments = fixture._workflow_comments(sibling, trigger)
		frappe.set_user(fixture.reviewer)

		with patch.object(workflow_scenario_actions, "_move_position",
			side_effect=frappe.ValidationError("Synthetic validation failure")):
			with self.assertRaisesRegex(workflow_scenario_actions.TimesheetTransitionError, "rolled back"):
				workflow_scenario_actions.recalculate_parent(fixture.parent.reload(), trigger, None)

		self.assertEqual(fixture.parent.reload().ut_status, "Draft")
		self.assertEqual(sibling.reload().status, "Rejected")
		self.assertEqual(trigger.reload().status, "Pending Approval")
		self.assertEqual(fixture._workflow_comments(sibling, trigger), comments)
