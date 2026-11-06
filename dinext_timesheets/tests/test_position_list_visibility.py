"""Execute real permission-aware list SQL against owned transactional records."""

from unittest.mock import patch

import frappe
from dinext_timesheets.patches.v1_0.visible_position_list import execute as convert
from dinext_timesheets.timesheet_settings import utp_list_conditions
from frappe.tests.utils import FrappeTestCase

MODULE = "dinext_timesheets.timesheet_settings"


class TestPositionListVisibility(FrappeTestCase):
	def setUp(self):
		self.previous_form = frappe.local.form_dict
		frappe.local.form_dict = frappe._dict(cmd="frappe.desk.reportview.get")
		self.prefix = "_Test Visibility " + frappe.generate_hash(length=10)
		self.pending = self.position("pending", "Pending Approval")
		self.approved = self.position("approved", "Approved")
		self.hidden = self.position("hidden", "Editing")
		self.blank = self.position("blank", "")
		self.null = self.position("null", None)
		self.rules = [
			{"position_status": "Approved", "open_wf_task": 0},
			{"position_status": "Pending Approval", "open_wf_task": 1},
		]
		self.rule_patch = patch(f"{MODULE}.visible_list_rules", side_effect=lambda: self.rules)
		self.rule_patch.start()

	def tearDown(self):
		self.rule_patch.stop()
		frappe.local.form_dict = self.previous_form

	def position(self, suffix, status):
		doc = frappe.get_doc(
			{
				"doctype": "User Timesheet Position",
				"name": self.prefix + suffix,
				"status": status,
			}
		)
		doc.db_insert()
		return doc.name

	def task(self, user="Administrator", status="Working", round_status="Open", **extra):
		doc = frappe.get_doc(
			{
				"doctype": "Workflow Task",
				"name": self.prefix + frappe.generate_hash(length=6),
				"doc": "User Timesheet Position",
				"wt_docname": self.pending,
				"reference_doctype": "User Timesheet Position",
				"reference_name": self.pending,
				"approver": user,
				"status": status,
				"round_status": round_status,
				**extra,
			}
		)
		doc.db_insert()
		return doc.name

	def rows(self, **kwargs):
		return frappe.get_list(
			"User Timesheet Position",
			filters={"name": ("like", self.prefix + "%")},
			fields=["name"],
			order_by="name asc",
			**kwargs,
		)

	def test_allowlist_requires_only_own_open_task(self):
		self.task(user="other@example.com")
		self.assertEqual([r.name for r in self.rows()], [self.approved])
		task = self.task()
		self.assertEqual({r.name for r in self.rows()}, {self.pending, self.approved})
		for status, round_status in [
			("Completed", "Open"),
			("Cancelled", "Open"),
			("Working", "Transitioned"),
			("Working", "Conflicted"),
			("Working", "Stalled"),
		]:
			frappe.db.set_value(
				"Workflow Task",
				task,
				{"status": status, "round_status": round_status},
				update_modified=False,
			)
			self.assertEqual([r.name for r in self.rows()], [self.approved])
		frappe.db.set_value(
			"Workflow Task",
			task,
			{"status": "Working", "round_status": "Open"},
			update_modified=False,
		)
		self.assertEqual({r.name for r in self.rows()}, {self.pending, self.approved})

	def test_unchecked_flag_does_not_require_a_task(self):
		self.rules[1]["open_wf_task"] = 0
		self.assertEqual({r.name for r in self.rows()}, {self.pending, self.approved})

	def test_empty_list_and_explicit_not_set(self):
		self.rules.clear()
		self.assertEqual(self.rows(), [])
		self.rules.append({"position_status": "Not Set", "open_wf_task": 0})
		self.assertEqual({r.name for r in self.rows()}, {self.blank, self.null})

	def test_duplicates_do_not_affect_counts_or_pagination(self):
		self.task()
		self.task()
		rows = self.rows()
		self.assertEqual(len(rows), 2)
		self.assertEqual(self.rows(limit_start=0, limit_page_length=1), rows[:1])
		self.assertEqual(self.rows(limit_start=1, limit_page_length=1), rows[1:])
		count = frappe.get_list(
			"User Timesheet Position",
			filters={"name": ("like", self.prefix + "%")},
			fields=["count(name) as count"],
		)[0].count
		self.assertEqual(count, 2)

	def test_gated_branch_cannot_bypass_other_filters(self):
		self.task()
		# An eligible pending position outside the caller's filter must not leak through OR.
		rows = frappe.get_list("User Timesheet Position", filters={"name": self.approved}, fields=["name"])
		self.assertEqual([r.name for r in rows], [self.approved])

	def test_user_argument_and_reference_type_are_respected(self):
		self.task(user="other@example.com", reference_doctype="Task")
		condition = utp_list_conditions(user="other@example.com")
		self.assertIn("other@example.com", condition)
		self.assertIn("User Timesheet Position", condition)
		self.assertEqual([r.name for r in self.rows()], [self.approved])

	def test_quotes_in_status_do_not_change_query_scope(self):
		self.rules[:] = [{"position_status": "Approved') OR 1=1 --", "open_wf_task": 0}]
		self.assertEqual(self.rows(), [])

	def test_filter_does_not_change_form_or_api_queries(self):
		frappe.local.form_dict = frappe._dict(cmd="frappe.client.get_list")
		self.assertEqual(len(self.rows()), 5)


class TestVisiblePositionMigration(FrappeTestCase):
	def test_conversion_preserves_rollup_rules_and_admin_empty_edit(self):
		doc = frappe.get_single("Timesheet Settings")
		keys = ("position_status", "threshold", "timesheet_status", "move_all_positions", "check_timesheet")
		rules = [{key: r.get(key) for key in keys} for r in doc.position_rules]
		doc.set("visible_list_statuses", [])
		doc.set(
			"hidden_list_statuses",
			[{"position_status": "Editing"}, {"position_status": "Not Set"}],
		)
		doc.save(ignore_permissions=True)
		frappe.db.set_single_value("Timesheet Settings", "position_list_visibility_migrated", 0)
		with patch(
			"dinext_timesheets.patches.v1_0.visible_position_list.position_workflow_states",
			return_value=["Editing", "Pending Approval", "Approved"],
		):
			convert()
		doc = frappe.get_single("Timesheet Settings")
		self.assertEqual(
			[(r.position_status, r.open_wf_task) for r in doc.visible_list_statuses],
			[("Pending Approval", 1), ("Approved", 0)],
		)
		self.assertEqual([{key: r.get(key) for key in keys} for r in doc.position_rules], rules)
		doc.set("visible_list_statuses", [])
		doc.save(ignore_permissions=True)
		convert()
		self.assertEqual(frappe.get_single("Timesheet Settings").visible_list_statuses, [])

	def test_old_empty_exclusion_becomes_all_known_states_and_blank(self):
		doc = frappe.get_single("Timesheet Settings")
		doc.set("visible_list_statuses", [])
		doc.set("hidden_list_statuses", [])
		doc.save(ignore_permissions=True)
		frappe.db.set_single_value("Timesheet Settings", "position_list_visibility_migrated", 0)
		with patch(
			"dinext_timesheets.patches.v1_0.visible_position_list.position_workflow_states",
			return_value=["Editing", "Approved"],
		):
			convert()
		self.assertEqual(
			[r.position_status for r in frappe.get_single("Timesheet Settings").visible_list_statuses],
			["Editing", "Approved", "Not Set"],
		)
