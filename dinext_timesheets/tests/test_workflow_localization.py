"""Regression coverage for Timesheet decisions across workflow label changes."""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe
from dinext_common.workflow_approval import engine
from dinext_common.workflow_approval.policy import transition_semantic_hash

from dinext_timesheets.workflow_localization import label_rules


class TestTimesheetWorkflowLocalization(TestCase):
	def setUp(self):
		self.workflow = "UTP Workflow"
		self.enterContext(patch.object(frappe, "local", SimpleNamespace(site="test")))
		self.enterContext(
			patch.object(
				frappe,
				"get_hooks",
				return_value={self.workflow: ["dinext_timesheets.workflow_localization.label_rules"]},
			)
		)
		self.enterContext(patch.object(frappe, "get_attr", return_value=label_rules))
		self.previous = engine._transition_dict(
			{
				"state": "Pending Approval",
				"action": "Согласовано",
				"next_state": "Approved",
				"allowed": "Dinext_UTP_Appoval",
				"condition": "doc.user != frappe.session.user",
				"custom_transition_uuid": "approval-transition",
				"custom_parallel_approval_policy": "All",
			}
		)
		self.current = {**self.previous, "action": "Approve"}
		self.current["transition_semantic_hash"] = transition_semantic_hash(self.current)

	def test_stale_utp_manifest_requires_evidence_from_every_eligible_approver(self):
		from frappe import _dict

		from dinext_timesheets.workflow_localization import collect_legacy_evidence, recover_legacy_transition

		source = {
			**self.previous,
			"action": "Согласовано",
			"state": "На согласовании",  # noqa: RUF001
			"next_state": "Согласовано",
		}
		old_hash = transition_semantic_hash(source)
		uuid = self.current["transition_uuid"]
		tasks = []
		for approver in ("alex@example.com", "elena@example.com"):
			option = _dict(
				{**source, "action": "Approve", "transition_semantic_hash": old_hash, "threshold": 2}
			)
			option.as_dict = lambda option=option: option
			tasks.append(
				_dict(
					workflow=self.workflow,
					approver=approver,
					status="Working",
					round_manifest="the same snapshot",
					available_workflow_transitions=[option],
				)
			)
		manifest = {
			**self.previous,
			"transition_semantic_hash": "a stale manifest hash",
			"eligible_approvers": [t.approver for t in tasks],
			"threshold": 2,
		}
		self.assertIsNone(recover_legacy_transition(manifest, self.current, {}))
		proven = collect_legacy_evidence(tasks, {uuid: self.current})[uuid]
		self.assertEqual(
			recover_legacy_transition(manifest, self.current, proven)["transition_semantic_hash"],
			self.current["transition_semantic_hash"],
		)
		carried = _dict(
			workflow=self.workflow,
			approver="former@example.com",
			status="Completed",
			transition_uuid=uuid,
			round_manifest="the same snapshot",
			available_workflow_transitions=[],
		)
		self.assertNotIn(uuid, collect_legacy_evidence([*tasks, carried], {uuid: self.current}))
		tasks[0].available_workflow_transitions[0].transition_semantic_hash = "unproven"
		proven = collect_legacy_evidence(tasks, {uuid: self.current})[uuid]
		self.assertIsNone(recover_legacy_transition(manifest, self.current, proven))
