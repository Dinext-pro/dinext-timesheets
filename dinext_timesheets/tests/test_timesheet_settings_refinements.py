"""Current Workflow choices and explicit Pending Approval defaults."""

from types import SimpleNamespace
from unittest.mock import patch

import frappe
from dinext_timesheets.timesheet_settings import (
	position_workflow_states,
	utp_state_query,
	visible_list_rules,
	visible_status_options,
)
from dinext_timesheets.timesheet_status import DEFAULT_VISIBLE_LIST_STATUSES
from frappe.tests.utils import FrappeTestCase


class TestVisibilityDefaults(FrappeTestCase):
	def test_pending_approval_defaults_on_and_other_states_default_off(self):
		defaults = {r["position_status"]: r["open_wf_task"] for r in DEFAULT_VISIBLE_LIST_STATUSES}
		self.assertEqual(defaults["Pending Approval"], 1)
		self.assertEqual(defaults["Approved"], 0)

	def test_saved_overrides_remain_explicit(self):
		doc = SimpleNamespace(
			visible_list_statuses=[
				frappe._dict(position_status="Pending Approval", open_wf_task=0),
				frappe._dict(position_status="Approved", open_wf_task=1),
			]
		)
		with patch("dinext_timesheets.timesheet_settings._settings_doc", return_value=doc):
			self.assertEqual(
				visible_list_rules(),
				[
					{"position_status": "Pending Approval", "open_wf_task": 0},
					{"position_status": "Approved", "open_wf_task": 1},
				],
			)


class TestLiveWorkflowStatusChoices(FrappeTestCase):
	def setUp(self):
		self.savepoint = "live_ts_statuses"
		frappe.db.savepoint(self.savepoint)
		self.prefix = "_Test TS States " + frappe.generate_hash(length=8)
		# All changes are uncommitted and rolled back. Other sessions retain the real active Workflow.
		for name in frappe.get_all(
			"Workflow", filters={"document_type": "User Timesheet Position", "is_active": 1}, pluck="name"
		):
			frappe.db.set_value("Workflow", name, "is_active", 0, update_modified=False)
		self.states = [self.prefix + n for n in [" A", " B", " C", " Inactive"]]
		for name in self.states:
			frappe.get_doc(
				{"doctype": "Workflow State", "name": name, "workflow_state_name": name}
			).db_insert()
		self.workflow = self.make_workflow(" Active", [self.states[0], self.states[1]], 1)
		self.make_workflow(" Inactive", [self.states[3]], 0)

	def tearDown(self):
		frappe.db.rollback(save_point=self.savepoint)

	def make_workflow(self, suffix, states, active):
		doc = frappe.get_doc(
			{
				"doctype": "Workflow",
				"name": self.prefix + suffix,
				"workflow_name": self.prefix + suffix,
				"document_type": "User Timesheet Position",
				"is_active": active,
				"states": [{"state": s, "doc_status": "0", "allow_edit": "All"} for s in states],
			}
		)
		doc.db_insert()
		for row in doc.states:
			row.db_insert()
		return doc

	def assert_choices(self, expected):
		self.assertEqual(position_workflow_states(), expected)
		self.assertEqual(visible_status_options(), [*expected, "Not Set"])
		self.assertEqual([r[0] for r in utp_state_query("Workflow State", "", "name", 0, 100, {})], expected)

	def test_current_states_are_read_again_after_state_changes(self):
		self.assert_choices(self.states[:2])
		frappe.db.set_value(
			"Workflow Document State",
			self.workflow.states[1].name,
			"state",
			self.states[2],
			update_modified=False,
		)
		self.assert_choices([self.states[0], self.states[2]])
		frappe.db.delete("Workflow Document State", {"name": self.workflow.states[0].name})
		self.assert_choices([self.states[2]])

	def test_switching_active_workflow_updates_both_selectors(self):
		frappe.db.set_value("Workflow", self.workflow.name, "is_active", 0, update_modified=False)
		frappe.db.set_value("Workflow", self.prefix + " Inactive", "is_active", 1, update_modified=False)
		self.assert_choices([self.states[3]])
