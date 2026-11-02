"""Approval reuse through real position saves, votes, and rejection callbacks."""

from unittest.mock import patch

import frappe
from dinext_common.workflow_approval import engine
from frappe.tests.utils import FrappeTestCase


class TestPositionApprovalReuse(FrappeTestCase):
	def setUp(self):
		super().setUp()
		self.token = frappe.generate_hash(length=10)
		self.savepoint = "fingerprint_" + self.token
		frappe.db.savepoint(self.savepoint)
		self.addCleanup(self._cleanup)
		self.previous_flag = frappe.conf.get("enable_parallel_workflow_approval")
		frappe.conf.enable_parallel_workflow_approval = False
		self.flags = patch.dict(frappe.flags, {"in_timesheet_approval_cascade": True, "mute_emails": True})
		self.flags.start()
		self.addCleanup(self.flags.stop)
		self.jobs = patch.object(frappe, "enqueue")
		self.jobs.start()
		self.addCleanup(self.jobs.stop)
		# Parent calendar/accounting setup is independent of position approval content.
		parent_events = "dinext_timesheets.dinext_timesheets.user_timesheet.events.user_timesheet"
		self.enterContext(patch(parent_events + ".calculate_ut_hours"))
		self.enterContext(patch(parent_events + ".maybe_create_or_cancel_journal_entries"))
		self.role = "_Test FP " + self.token
		frappe.get_doc({"doctype": "Role", "role_name": self.role}).insert(ignore_permissions=True)
		self.users = []
		for number in (1, 2):
			user = frappe.get_doc(
				{
					"doctype": "User",
					"email": f"fp-{self.token}-{number}@example.com",
					"first_name": f"Fingerprint approver {number}",
					"enabled": 1,
					"user_type": "System User",
					"send_welcome_email": 0,
					"roles": [
						{"role": role} for role in (self.role, "System Manager", "Dinext_UT_Full_Access")
					],
				}
			).insert(ignore_permissions=True)
			self.users.append(user.name)
		for state in ("Pending Approval", "Approved", "Rejected"):
			if not frappe.db.exists("Workflow State", state):
				frappe.get_doc({"doctype": "Workflow State", "workflow_state_name": state}).insert(
					ignore_permissions=True
				)
		self.actions = {}
		for action in ("Approve", "Reject", "Resubmit"):
			name = f"_Test FP {action} {self.token}"
			frappe.get_doc({"doctype": "Workflow Action Master", "workflow_action_name": name}).insert(
				ignore_permissions=True
			)
			self.actions[action] = name
		self.workflow = frappe.get_doc(
			{
				"doctype": "Workflow",
				"workflow_name": "_Test FP " + self.token,
				"document_type": "User Timesheet Position",
				"workflow_state_field": "workflow_state",
				"is_active": 1,
				"send_email_alert": 0,
				"states": [
					{
						"state": state,
						"doc_status": "0",
						"allow_edit": "System Manager",
						"update_field": "status",
						"update_value": state,
					}
					for state in ("Pending Approval", "Approved", "Rejected")
				],
				"transitions": [
					{
						"state": "Pending Approval",
						"action": self.actions["Approve"],
						"next_state": "Approved",
						"allowed": self.role,
						"allow_self_approval": 1,
						"custom_parallel_approval_policy": "All",
						"custom_auto_complete_unchanged": 1,
						"custom_transition_uuid": "approve-" + self.token,
					},
					{
						"state": "Pending Approval",
						"action": self.actions["Reject"],
						"next_state": "Rejected",
						"allowed": self.role,
						"allow_self_approval": 1,
						"custom_comment_is_required": 1,
						"custom_parallel_approval_policy": "Any",
						"custom_transition_uuid": "reject-" + self.token,
					},
					{
						"state": "Rejected",
						"action": self.actions["Resubmit"],
						"next_state": "Pending Approval",
						"allowed": self.role,
						"allow_self_approval": 1,
						"custom_parallel_approval_policy": "Any",
						"custom_transition_uuid": "resubmit-" + self.token,
					},
				],
			}
		).insert(ignore_permissions=True)
		frappe.clear_cache(doctype="User Timesheet Position")
		self.parent = frappe.get_doc(
			{
				"doctype": "User Timesheet",
				"name": "_Test FP Parent " + self.token,
				"timesheet_from": "Administrator",
				"ts_valid_from": "2039-01-03",
				"ts_valid_for": "2039-01-09",
				"ut_status": "Pending Approval",
				"user_group": "_Test Group",
			}
		)
		self.parent.db_insert()
		frappe.conf.enable_parallel_workflow_approval = True
		self.positions = [self._position(number) for number in (1, 2)]

	def _cleanup(self):
		frappe.set_user("Administrator")
		frappe.conf.enable_parallel_workflow_approval = self.previous_flag
		frappe.db.rollback(save_point=self.savepoint)
		frappe.clear_cache(doctype="User Timesheet Position")

	def _position(self, number):
		position = frappe.get_doc(
			{
				"doctype": "User Timesheet Position",
				"name": f"_Test FP Position {self.token}-{number}",
				"user_timesheet": self.parent.name,
				"user": "Administrator",
				"user_group": "_Test Group",
				"workflow_state": "Pending Approval",
				"status": "Pending Approval",
				"all_hours": 8.0,
				"period": "2039-01-01",
				"reject_reason": "",
			}
		)
		position.db_insert()
		row = position.append(
			"table",
			{"date": "2039-01-03", "hours": 8.0, "description": "Reported work", "utilized_hours": 8.0},
		)
		row.db_insert()
		position.save(ignore_permissions=True)
		return position

	def task(self, position, user):
		name = frappe.get_all(
			"Workflow Task",
			filters={
				"reference_doctype": position.doctype,
				"reference_name": position.name,
				"approver": user,
				"workflow_state": "Pending Approval",
				"round_status": "Open",
			},
			pluck="name",
			limit=1,
		)[0]
		return frappe.get_doc("Workflow Task", name)

	def vote(self, position, user, action):
		frappe.set_user(user)
		task = self.task(position, user)
		engine.cast_vote(
			task.name, action=self.actions[action], comment="Check this work" if action == "Reject" else ""
		)
		return task.reload()

	def reject_after_approval(self, *, legacy=False):
		approvals = []
		for position in self.positions:
			if legacy:
				with patch.object(engine, "_fingerprint_exclusions", return_value=set()):
					approvals.append(self.vote(position, self.users[0], "Approve"))
			else:
				approvals.append(self.vote(position, self.users[0], "Approve"))
			self.vote(position, self.users[1], "Reject")
			self.assertEqual(position.reload().reject_reason, "Check this work")
			self.assertEqual(position.status, "Rejected")
		return approvals

	def resubmit(self):
		for position in self.positions:
			engine.apply_domain_transition(
				position.doctype,
				position.name,
				"Pending Approval",
				reason="Resubmit unchanged work",
				actor=self.users[0],
			)

	def test_unchanged_resubmission_reuses_approval_and_waits_for_all(self):
		approvals = self.reject_after_approval()
		self.resubmit()
		for position, prior in zip(self.positions, approvals, strict=True):
			current = self.task(position, self.users[0])
			self.assertEqual(current.status, "Completed")
			self.assertEqual(current.completion_source, "Automatic Unchanged")
			self.assertEqual(current.reused_from_workflow_task, prior.name)
			self.assertEqual(current.content_fingerprint, prior.content_fingerprint)
			self.assertEqual(self.task(position, self.users[1]).status, "Working")
			self.assertEqual(position.reload().workflow_state, "Pending Approval")
			self.assertTrue(
				frappe.db.exists(
					"Comment",
					{
						"reference_doctype": position.doctype,
						"reference_name": position.name,
						"comment_type": "Workflow",
						"content": ("like", "%automatically reused action%"),
					},
				)
			)
			self.assertFalse(
				frappe.db.exists("ToDo", {"reference_type": "Workflow Task", "reference_name": current.name})
			)
			self.vote(position, self.users[1], "Approve")
			self.assertEqual(position.reload().workflow_state, "Approved")

	def test_changed_work_stays_pending_while_unchanged_position_reuses_vote(self):
		self.reject_after_approval()
		frappe.set_user("Administrator")
		changed = self.positions[1].reload()
		changed.table[0].hours = 7.0
		changed.save(ignore_permissions=True)
		self.resubmit()
		self.assertEqual(self.task(self.positions[0], self.users[0]).status, "Completed")
		self.assertEqual(self.task(changed, self.users[0]).status, "Working")

	def test_disabled_automatic_completion_keeps_both_approvers_pending(self):
		self.reject_after_approval()
		frappe.set_user("Administrator")
		self.workflow.transitions[0].custom_auto_complete_unchanged = 0
		self.workflow.save(ignore_permissions=True)
		frappe.clear_cache(doctype="User Timesheet Position")
		self.resubmit()
		for position in self.positions:
			for user in self.users:
				self.assertEqual(self.task(position, user).status, "Working")

	def test_old_votes_remain_unchanged_and_are_not_reused(self):
		approvals = self.reject_after_approval(legacy=True)
		before = [(row.name, row.content_fingerprint, row.completed_at) for row in approvals]
		self.resubmit()
		for position in self.positions:
			self.assertEqual(self.task(position, self.users[0]).status, "Working")
		for name, digest, completed_at in before:
			row = frappe.get_doc("Workflow Task", name)
			self.assertEqual(
				(row.status, row.content_fingerprint, row.completed_at), ("Completed", digest, completed_at)
			)
