# Copyright (c) 2026, Dinext and contributors

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from dinext_timesheets.patches.v1_0.english_timesheet_statuses import execute
from dinext_timesheets.timesheet_settings import (
	hidden_list_statuses,
	hidden_status_values,
	parent_position_target,
	position_rules,
	utp_list_conditions,
	validate_timesheet_settings,
)
from dinext_timesheets.timesheet_status import (
	UTP_STATUS_FROM_RUSSIAN,
	first_matching_rule,
)


def _rule(position_status, timesheet_status, threshold):
	return {
		"position_status": position_status,
		"timesheet_status": timesheet_status,
		"threshold": threshold,
	}


RULES = [
	_rule("Rejected", "Rejected", "Any"),
	_rule("Approved", "Approved", "All"),
	_rule("Editing", "Rework", "Any"),
]


class TestTimesheetRuleMatcher(FrappeTestCase):
	def test_empty_counts_match_nothing(self):
		self.assertIsNone(first_matching_rule(RULES, {}))

	def test_one_rejected_among_approved_wins_first(self):
		rule = first_matching_rule(RULES, {"Rejected": 1, "Approved": 2})
		self.assertEqual(rule["timesheet_status"], "Rejected")

	def test_all_but_one_approved_does_not_approve_the_timesheet(self):
		rule = first_matching_rule(RULES, {"Approved": 2, "Editing": 1})
		self.assertEqual(rule["timesheet_status"], "Rework")
		self.assertIsNone(
			first_matching_rule([_rule("Approved", "Approved", "All")], {"Approved": 2, "Editing": 1})
		)

	def test_pending_positions_do_not_set_the_timesheet(self):
		self.assertIsNone(first_matching_rule(RULES, {"Pending Approval": 3}))
		self.assertIsNone(first_matching_rule(RULES, {"Pending Approval": 1, "Approved": 1}))

	def test_later_rule_is_not_used_when_an_earlier_one_matches(self):
		rule = first_matching_rule(RULES, {"Rejected": 1, "Editing": 1})
		self.assertEqual(rule["position_status"], "Rejected")

	def test_unknown_status_is_ignored_by_the_caller_filter(self):
		rules = [_rule("Legacy", "Draft", "Any"), *_rule_tail()]
		usable = [row for row in rules if row["position_status"] != "Legacy"]
		self.assertEqual(
			first_matching_rule(usable, {"Legacy": 2, "Editing": 1})["timesheet_status"],
			"Rework",
		)


def _rule_tail():
	return [_rule("Editing", "Rework", "Any")]


class TestTimesheetSettingsValidation(FrappeTestCase):
	def _doc(self, position_rows, parent_rows=None):
		return SimpleNamespace(
			position_rules=[SimpleNamespace(**row) for row in position_rows],
			parent_rules=[SimpleNamespace(**row) for row in (parent_rows or [])],
		)

	def test_duplicate_position_status_is_rejected(self):
		doc = self._doc(
			[
				{"position_status": "Editing", "timesheet_status": "Rework", "threshold": "Any"},
				{"position_status": "Editing", "timesheet_status": "Draft", "threshold": "All"},
			]
		)
		with (
			patch(
				"dinext_timesheets.timesheet_settings.position_workflow_states",
				return_value=["Editing", "Approved"],
			),
			self.assertRaises(frappe.ValidationError),
		):
			validate_timesheet_settings(doc)

	def test_state_outside_the_workflow_is_rejected(self):
		doc = self._doc(
			[
				{
					"position_status": "Not A State",
					"timesheet_status": "Draft",
					"threshold": "Any",
				}
			]
		)
		with (
			patch(
				"dinext_timesheets.timesheet_settings.position_workflow_states",
				return_value=["Editing"],
			),
			self.assertRaises(frappe.ValidationError),
		):
			validate_timesheet_settings(doc)

	def test_missing_singleton_uses_defaults_and_saved_empty_does_not(self):
		with patch("dinext_timesheets.timesheet_settings.frappe.db.exists", return_value=False):
			self.assertEqual(len(position_rules()), 3)
			self.assertEqual(parent_position_target("Pending Approval"), "Pending Approval")
			self.assertEqual(hidden_list_statuses(), ["Editing", "Not Set"])
		empty = SimpleNamespace(
			position_rules=[],
			parent_rules=[],
			hidden_list_statuses=[],
		)
		with (
			patch("dinext_timesheets.timesheet_settings.frappe.db.exists", return_value=True),
			patch("dinext_timesheets.timesheet_settings.frappe.get_single", return_value=empty),
		):
			self.assertEqual(position_rules(), [])
			self.assertEqual(hidden_list_statuses(), [])

	def test_not_set_is_hidden_once_and_rejected_on_a_position_rule(self):
		hidden = SimpleNamespace(
			position_rules=[],
			parent_rules=[],
			hidden_list_statuses=[
				SimpleNamespace(position_status="Editing"),
				SimpleNamespace(position_status="Not Set"),
			],
		)
		with patch(
			"dinext_timesheets.timesheet_settings.position_workflow_states",
			return_value=["Editing"],
		):
			validate_timesheet_settings(hidden)
		duplicate = SimpleNamespace(
			position_rules=[],
			parent_rules=[],
			hidden_list_statuses=[
				SimpleNamespace(position_status="Not Set"),
				SimpleNamespace(position_status="Not Set"),
			],
		)
		with (
			patch(
				"dinext_timesheets.timesheet_settings.position_workflow_states",
				return_value=["Editing"],
			),
			self.assertRaises(frappe.ValidationError),
		):
			validate_timesheet_settings(duplicate)
		position_rule = self._doc(
			[{"position_status": "Not Set", "timesheet_status": "Draft", "threshold": "Any"}]
		)
		with (
			patch(
				"dinext_timesheets.timesheet_settings.position_workflow_states",
				return_value=[],
			),
			self.assertRaises(frappe.ValidationError),
		):
			validate_timesheet_settings(position_rule)

	def test_list_condition_excludes_hidden_statuses_only_for_the_position_list(self):
		previous = frappe.local.form_dict
		try:
			frappe.local.form_dict = frappe._dict(cmd="frappe.desk.reportview.get")
			with patch(
				"dinext_timesheets.timesheet_settings.hidden_list_statuses",
				return_value=["Editing"],
			):
				self.assertEqual(
					utp_list_conditions(),
					"ifnull(`tabUser Timesheet Position`.`status`, '') not in ('Editing')",
				)
			with patch(
				"dinext_timesheets.timesheet_settings.hidden_list_statuses",
				return_value=["Editing", "Not Set"],
			):
				self.assertEqual(
					utp_list_conditions(),
					"ifnull(`tabUser Timesheet Position`.`status`, '') not in ('Editing', '')",
				)
			with patch(
				"dinext_timesheets.timesheet_settings.hidden_list_statuses",
				return_value=[],
			):
				self.assertEqual(utp_list_conditions(), "")
			frappe.local.form_dict = frappe._dict(cmd="frappe.client.get_list")
			with patch(
				"dinext_timesheets.timesheet_settings.hidden_list_statuses",
				return_value=["Editing", "Not Set"],
			):
				self.assertEqual(utp_list_conditions(), "")
		finally:
			frappe.local.form_dict = previous
		self.assertEqual(hidden_status_values(["Not Set"]), [""])
		self.assertEqual(hidden_status_values(["Editing"]), ["Editing"])


class TestEnglishStatusPatch(FrappeTestCase):
	def test_russian_position_status_is_rewritten_once(self):
		name = frappe.db.get_value("User Timesheet Position", {}, "name")
		if not name:
			self.skipTest("no position on the site")
		original = frappe.db.get_value("User Timesheet Position", name, "status")
		frappe.db.set_value(
			"User Timesheet Position",
			name,
			"status",
			"Редактирование",
			update_modified=False,
		)
		state_row = frappe.db.get_value(
			"Workflow Document State",
			{"parent": "UTP Workflow", "parenttype": "Workflow", "state": "Rejected"},
			["name", "update_value"],
			as_dict=True,
		)
		if state_row:
			frappe.db.set_value(
				"Workflow Document State",
				state_row.name,
				"update_value",
				"Отклонено",
				update_modified=False,
			)
		execute()
		self.assertEqual(
			frappe.db.get_value("User Timesheet Position", name, "status"),
			UTP_STATUS_FROM_RUSSIAN["Редактирование"],
		)
		execute()
		self.assertEqual(
			frappe.db.get_value("User Timesheet Position", name, "status"),
			"Editing",
		)
		if state_row:
			self.assertEqual(
				frappe.db.get_value("Workflow Document State", state_row.name, "update_value"),
				"Rejected",
			)
			frappe.db.set_value(
				"Workflow Document State",
				state_row.name,
				"update_value",
				state_row.update_value,
				update_modified=False,
			)
		frappe.db.set_value(
			"User Timesheet Position",
			name,
			"status",
			original,
			update_modified=False,
		)

	def test_russian_round_manifest_matches_the_current_transition(self):
		task_name = frappe.db.get_value(
			"Workflow Task",
			{"reference_doctype": "User Timesheet Position"},
			"name",
		)
		transition = frappe.db.get_value(
			"Workflow Transition",
			{
				"parent": "UTP Workflow",
				"parenttype": "Workflow",
				"state": "Rejected",
				"action": "Редактировать",
			},
			"custom_transition_uuid",
		)
		if not task_name or not transition:
			self.skipTest("position workflow task or rejected edit transition is missing")
		original_manifest = frappe.db.get_value("Workflow Task", task_name, "round_manifest")
		original_next = frappe.db.get_value("Workflow Task", task_name, "next_state")
		frappe.db.set_value(
			"Workflow Task",
			task_name,
			{
				"round_manifest": json.dumps(
					{
						"version": 1,
						"transitions": [
							{
								"action": "Редактировать",
								"allowed": "Dinext_Worker",
								"state": "Отклонено",
								"next_state": "Редактирование",
								"policy": "Any",
								"transition_semantic_hash": "stale",
								"transition_uuid": transition,
							}
						],
					}
				),
				"next_state": "Редактирование",
			},
			update_modified=False,
		)
		execute()
		stored = json.loads(frappe.db.get_value("Workflow Task", task_name, "round_manifest"))
		row = stored["transitions"][0]
		self.assertEqual(row["state"], "Rejected")
		self.assertEqual(row["next_state"], "Editing")
		self.assertEqual(row["action"], "Редактировать")
		self.assertEqual(row["allowed"], "Dinext_Worker")
		self.assertEqual(row["transition_uuid"], transition)
		from dinext_common.workflow_approval.engine import (
			_configured_transition_hashes,
			manifest_matches_configuration,
		)
		from frappe.model.workflow import get_workflow

		hashes = _configured_transition_hashes(get_workflow("User Timesheet Position"), "Rejected")
		self.assertEqual(row["transition_semantic_hash"], hashes[transition])
		self.assertTrue(manifest_matches_configuration(stored, hashes))
		self.assertEqual(frappe.db.get_value("Workflow Task", task_name, "next_state"), "Editing")
		first_manifest = frappe.db.get_value("Workflow Task", task_name, "round_manifest")
		execute()
		self.assertEqual(
			frappe.db.get_value("Workflow Task", task_name, "round_manifest"),
			first_manifest,
		)
		frappe.db.set_value(
			"Workflow Task",
			task_name,
			{"round_manifest": original_manifest, "next_state": original_next},
			update_modified=False,
		)

	def test_form_sources_compare_english_keys(self):
		root = Path(frappe.get_app_path("dinext_timesheets", "public", "js", "user_timesheet"))
		model = (root / "model.js").read_text()
		dashboard = (root / "dashboard.js").read_text()
		colors = (root / "list" / "status_color.js").read_text()
		for source in (model, dashboard, colors):
			self.assertNotIn("Черновик", source)
			self.assertNotIn("На доработке", source)
		self.assertIn('"Draft"', model)
		self.assertIn('"Rework"', model)
		self.assertIn('"Approved"', colors)
