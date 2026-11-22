"""Preflight rules for moving position Workflow state to status."""

from copy import deepcopy
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

import frappe
from frappe.utils import get_datetime


class TestPositionStatusMigration(TestCase):
	def migration(self):
		from dinext_timesheets.patches.v1_0 import unify_utp_workflow_status

		return unify_utp_workflow_status

	def test_rewrites_only_static_document_field_references(self):
		migration = self.migration()
		old = '''doc.workflow_state == "В работе" and doc.get("workflow_state") == doc['workflow_state']'''
		self.assertEqual(
			migration.rewrite_condition(old, "workflow_state", {"workflow_state"}),
			'''doc.status == "В работе" and doc.get('status') == doc['status']''',
		)
		self.assertEqual(
			migration.rewrite_condition('doc.name == "workflow_state elsewhere"', "workflow_state", {"workflow_state"}),
			'doc.name == "workflow_state elsewhere"',
		)

	def test_rejects_conditions_with_unproven_legacy_field_access(self):
		migration = self.migration()
		for condition in (
			'doc.get("workflow_" + "state") == "Editing"',
			'doc["workflow_" + "state"] == "Editing"',
			'frappe.db.get_value("User Timesheet Position", doc.name, "workflow_state") == "Editing"',
			'doc.custom_other_state == "Editing"',
		):
			with self.subTest(condition=condition), self.assertRaises(ValueError):
				migration.rewrite_condition(condition, "workflow_state", {"workflow_state", "custom_other_state"})

	def test_refuses_to_merge_conditions_reading_the_two_statuses_separately(self):
		migration = self.migration()
		for canonical in ("doc.status", "doc.get('status')", "doc['status']"):
			with self.subTest(canonical=canonical), self.assertRaises(ValueError):
				migration.rewrite_condition(
					f"doc.workflow_state == 'Pending Approval' and {canonical} == 'Editing'",
					"workflow_state", {"workflow_state"},
				)

	def test_live_round_refuses_condition_using_the_stale_status_mirror(self):
		migration = self.migration()
		workflow = frappe._dict(
			workflow_state_field="workflow_state",
			states=[],
			transitions=[frappe._dict(state="Pending Approval", condition="doc.status == 'Editing'")],
		)
		source = frappe._dict(name="UTP-STALE", status="Editing", workflow_state="Pending Approval",
			meta=frappe._dict(fields=[]))
		projected = frappe._dict(status="Pending Approval")
		plan = migration.MigrationPlan(retired_fields={"workflow_state"})
		with self.assertRaises(migration.MigrationBlocked):
			migration._check_round_identity(source, workflow, workflow, projected, plan, [])

	def test_accepts_stored_state_from_the_pinned_scheme_over_a_stale_status_mirror(self):
		migration = self.migration()
		workflow = frappe._dict(
			name="Custom position scheme",
			workflow_state_field="custom_position_state",
			states=[frappe._dict(state="Under Audit", doc_status=0)],
		)
		position = frappe._dict(
			name="UTP-1", docstatus=0, status="Editing", custom_position_state="Under Audit",
		)
		process = frappe._dict(name="Process-1", workflow=workflow.name, current_state="Under Audit")
		tasks = [frappe._dict(
			approval_round_id="Round-1", workflow_process=process.name, workflow=workflow.name,
			workflow_state="Under Audit", round_status="Open",
		)]
		self.assertEqual(
			migration.confirm_state(position, workflow, process, tasks, {"Editing", "Under Audit"}),
			"Under Audit",
		)

	def test_refuses_missing_or_conflicting_state_with_a_live_round(self):
		migration = self.migration()
		workflow = frappe._dict(
			name="UTP Workflow", workflow_state_field="workflow_state",
			states=[frappe._dict(state=state, doc_status=0) for state in ("Editing", "Pending Approval")],
		)
		position = frappe._dict(name="UTP-2", docstatus=0, status="Pending Approval")
		task = frappe._dict(
			approval_round_id="Round-2", workflow_process=None, workflow=workflow.name,
			workflow_state="Pending Approval", round_status="Open",
		)
		for old_state in (None, "Editing"):
			position.workflow_state = old_state
			with self.subTest(old_state=old_state), self.assertRaises(migration.MigrationBlocked):
				migration.confirm_state(position, workflow, None, [task], {"Editing", "Pending Approval"})

	def test_refuses_to_touch_a_finalizing_round(self):
		migration = self.migration()
		workflow = frappe._dict(
			name="UTP Workflow", workflow_state_field="workflow_state",
			states=[frappe._dict(state="Pending Approval", doc_status=0)],
		)
		position = frappe._dict(name="UTP-3", docstatus=0, status="Pending Approval", workflow_state="Pending Approval")
		task = frappe._dict(
			approval_round_id="Round-3", workflow_process=None, workflow=workflow.name,
			workflow_state="Pending Approval", round_status="Finalizing",
		)
		with self.assertRaises(migration.MigrationBlocked):
			migration.confirm_state(position, workflow, None, [task], {"Pending Approval"})

	def test_moves_active_round_condition_and_keeps_its_votes(self):
		from dinext_common.workflow_approval.engine import _transition_dict, build_round_manifest
		from dinext_common.workflow_approval.scenarios import read

		migration = self.migration()
		state = "Under Audit"
		old_condition = "doc.custom_position_state == 'Under Audit'"
		transition = frappe._dict(
			name="Transition-1", state=state, next_state="Approved", action="Approve",
			allowed="Timesheet Approver", custom_transition_uuid="transition-uuid",
			custom_parallel_approval_policy="All", condition=old_condition,
		)
		workflow = frappe._dict(
			name="Custom scheme", is_active=1, workflow_state_field="custom_position_state",
			states=[frappe._dict(state=state, doc_status=0, update_field="status", update_value=state)],
			transitions=[transition],
		)
		workflow.as_dict = lambda: deepcopy(workflow)
		source = frappe._dict(
			name="UTP-1", doctype=migration.POSITION, creation="2026-11-15 10:00:00",
			docstatus=0, status="Editing", custom_position_state=state,
			meta=SimpleNamespace(fields=[frappe._dict(fieldname="status", fieldtype="Select")]),
		)
		source.as_dict = lambda: frappe._dict(source)
		manifest, _ = build_round_manifest([{
			**_transition_dict(transition), "eligible_approvers": ["approver-1", "approver-2"],
		}])
		manifest["deadline_assignments"] = {"approver-2": {"due_at": "2026-11-20"}}
		old_hash = manifest["transitions"][0]["transition_semantic_hash"]
		new_hash = _transition_dict(frappe._dict(
			**{**transition, "condition": "doc.status == 'Under Audit'"},
		))["transition_semantic_hash"]
		identity = dict(transition_uuid=transition.custom_transition_uuid,
			transition_semantic_hash=old_hash, action=transition.action, next_state=transition.next_state)
		task_values = {
			"approval_round_id": "Round-1", "round_status": "Open", "workflow": workflow.name,
			"workflow_state": state, "round_manifest": frappe.as_json(manifest),
		}
		tasks = [
			frappe._dict(name="Accepted-vote", status="Completed", **task_values, **identity),
			frappe._dict(name="Pending-vote", status="Working", **task_values),
		]
		choices = [frappe._dict(name="Unchanged-choice-name", parent=tasks[1].name, state=state, **identity)]
		key = (source.name, get_datetime(source.creation))

		def plan_migration():
			plan = migration.MigrationPlan(retired_fields={"custom_position_state"})
			workflows = {workflow.name: workflow}
			projected = migration._plan_workflows(plan, workflows)
			with (
				patch.object(frappe, "get_all", side_effect=[[source.name], choices, []]),
				patch.object(frappe, "get_hooks", return_value=[]),
				patch.object(read, "load_documents", return_value={source.name: source}),
				patch.object(migration, "_active_evidence", return_value=({}, {}, {key: tasks})),
			):
				migration._plan_positions(plan, workflows, projected, {state})
			return plan

		for record in (tasks[0], choices[0]):
			with self.subTest(drift=record.name), patch.dict(record, transition_semantic_hash="unproven"):
				with self.assertRaises(migration.MigrationBlocked):
					plan_migration()

		plan = plan_migration()
		field = frappe._dict(fieldname="status", fieldtype="Link", options="Workflow State")
		db = Mock()
		with (
			patch.object(migration, "preflight", return_value=plan),
			patch.object(frappe, "get_doc", return_value=SimpleNamespace(fields=[field])),
			patch.object(frappe, "db", db),
			patch.object(frappe, "clear_cache"),
			patch.object(frappe, "clear_document_cache"),
		):
			migration.migrate()

		db.set_value.assert_any_call(
			migration.POSITION, {"name": ("in", [source.name])}, "status", state, update_modified=False,
		)
		writes = {(call.args[0], call.args[1]): call.args[2] for call in db.set_value.call_args_list
			if isinstance(call.args[1], str)}
		self.assertNotEqual(new_hash, old_hash)
		self.assertEqual(writes["Workflow Transition", transition.name], {"condition": "doc.status == 'Under Audit'"})
		self.assertEqual(writes["Available Workflow Transitions", choices[0].name], {"transition_semantic_hash": new_hash})
		for task in tasks:
			expected = {"round_manifest": frappe.parse_json(task.round_manifest)}
			expected["round_manifest"]["transitions"][0]["transition_semantic_hash"] = new_hash
			if task.status == "Completed":
				expected["transition_semantic_hash"] = new_hash
			stored = writes["Workflow Task", task.name]
			self.assertEqual({**stored, "round_manifest": frappe.parse_json(stored["round_manifest"])}, expected)
		self.assertTrue(all(call.kwargs["update_modified"] is False for call in db.set_value.call_args_list))
