import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import frappe

from dinext_timesheets.dinext_timesheets.user_timesheet.events import limits_notify


class TestWorkflowLimitNotifications(unittest.TestCase):
	def setUp(self):
		self.position = frappe._dict(
			doctype="User Timesheet Position",
			name="UTP-1",
			creation="2026-11-15 10:00:00",
			user_timesheet="UT-1",
			project="PRJ-1",
			document_name="TASK-1",
			project_role="Developer",
			status="Pending Approval",
		)

	def test_pending_round_only_schedules_dispatch_after_commit(self):
		with patch.object(frappe, "enqueue") as enqueue:
			limits_notify.schedule_limit_notice(self.position, "round-1")
			self.position.status = "Approved"
			limits_notify.schedule_limit_notice(self.position, "round-2")

		self.assertEqual(enqueue.call_count, 1)
		self.assertTrue(enqueue.call_args.kwargs["enqueue_after_commit"])
		self.assertEqual(enqueue.call_args.kwargs["round_id"], "round-1")

	def test_dispatch_skips_a_round_that_closed_before_commit(self):
		with (
			patch.object(limits_notify, "_lock_position", return_value=self.position),
			patch.object(limits_notify, "_is_current_round", return_value=False),
			patch.object(limits_notify, "_limit_notice") as notice,
		):
			limits_notify.notify_task_limit_if_pending("UTP-1", "round-1", self.position.creation)
		notice.assert_not_called()

	def test_repeated_dispatch_sends_at_most_once_per_recipient(self):
		ledger = SimpleNamespace(name="WT-1", notification_delivery_snapshot='{"existing":"retained"}')
		recipients = ["first@example.invalid", "second@example.invalid", "first@example.invalid"]
		sent = []

		def store(doctype, name, field, value, **kwargs):
			ledger.notification_delivery_snapshot = value

		with (
			patch.object(limits_notify, "_lock_position", return_value=self.position),
			patch.object(limits_notify, "_is_current_round", return_value=True),
			patch.object(limits_notify, "_lock_round_ledger", return_value=ledger),
			patch.object(limits_notify, "_limit_notice", return_value=({"completion_percentage": 120}, recipients)),
			patch.object(limits_notify, "_send_notice", side_effect=lambda pos, cfg, user: sent.append(user)),
			patch.object(frappe.db, "set_value", side_effect=store),
		):
			for _ in range(2):
				limits_notify.notify_task_limit_if_pending("UTP-1", "round-1", self.position.creation)
		self.assertEqual(sent, ["first@example.invalid", "second@example.invalid"])
		self.assertEqual(json.loads(ledger.notification_delivery_snapshot)["existing"], "retained")

	def test_used_method_notification_is_dispatched_with_automatic_trigger_disabled(self):
		notification = Mock(enabled=0, event="Method")
		todo = frappe._dict(flags=frappe._dict())
		config = {"notification": "Лимит по задаче", "planned_hours": 5}
		with patch.object(frappe, "get_doc", return_value=notification), patch.object(
			frappe, "new_doc", return_value=todo,
		):
			limits_notify._send_notice(self.position, config, "recipient@example.invalid")

		notification.send.assert_called_once_with(todo)
		self.assertEqual(todo.allocated_to, "recipient@example.invalid")
		self.assertEqual(todo.flags.context, {"planned_hours": 5})

	def test_legacy_after_save_script_remains_the_only_dispatcher_until_cutover(self):
		self.position.modified = self.position.creation
		self.position.get_doc_before_save = lambda: frappe._dict(status="Editing")
		legacy = {"User Timesheet Position": {"After Save": ["Task Limit Exceeded_V4"]}}
		with (
			patch("dinext_timesheets.workflow_approval._enabled", return_value=False),
			patch.object(limits_notify, "get_server_script_map", side_effect=[legacy, {}, {}]),
			patch.object(frappe, "enqueue") as enqueue,
		):
			limits_notify.notify_task_limit_exceeded(self.position)
			enqueue.assert_not_called()
			limits_notify.notify_task_limit_exceeded(self.position)
			limits_notify.notify_task_limit_exceeded(self.position)
		first, second = (call.kwargs for call in enqueue.call_args_list)
		self.assertEqual(first["job_id"], second["job_id"])
		self.assertTrue(first["deduplicate"] and first["enqueue_after_commit"])
