"""Plan/fact context parity through the real shared calculator aliases."""

from __future__ import annotations

import copy

import frappe
from frappe.tests.utils import FrappeTestCase
from project_workload_assignment.api import calculate_timesheet_limits, calculate_user_timesheet_limits

from dinext_timesheets.tests.limits_dialog_ui import (
	calculation_inputs,
	cleanup_limits_dialog,
	seed_limits_dialog,
	set_limits_case,
)


class TestLimitsDialogContract(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.fixture = seed_limits_dialog()
		self.positions = calculation_inputs(self.fixture["timesheet"])

	def tearDown(self):
		frappe.set_user("Administrator")
		cleanup_limits_dialog()

	def result(self, context, *, positions=None, alias=calculate_user_timesheet_limits):
		f = self.fixture
		if context == "tree":
			args = {
				"timesheet_name": "",
				"positions": [{"name": f["task"], "document_name": f["task"], "project": f["project"]}],
			}
		elif context == "list":
			args = {
				"timesheet_name": "",
				"positions": [
					{key: value for key, value in row.items() if key != "details"}
					for row in self.positions
					if row["name"] == f["position"]
				],
			}
		else:
			args = {"timesheet_name": f["timesheet"], "positions": positions or self.positions}
		previous = getattr(frappe.local, "form_dict", frappe._dict())
		try:
			frappe.local.form_dict = frappe._dict(args)
			rows = alias()
		finally:
			frappe.local.form_dict = previous
		return next(
			row
			for row in rows
			if row["role"] == f["role"] and (context == "tree" or row["position"] == f["position"])
		)

	def test_saved_form_list_and_tree_have_the_same_plan_and_fact(self):
		keys = (
			"planned_hours",
			"forecast_hours",
			"completion_percentage",
			"display_completion_percentage",
			"total_hours",
			"hours_data",
			"status_percentages",
			"user_totals",
			"status",
			"limit",
			"plan_sources",
		)
		results = []
		for context in ("form", "list", "tree"):
			row = self.result(context)
			results.append({key: row[key] for key in keys})
		self.assertEqual(results[0], results[1])
		self.assertEqual(results[0], results[2])
		self.assertEqual(results[0]["planned_hours"], 280)
		self.assertEqual(results[0]["forecast_hours"], 300)
		self.assertEqual(results[0]["total_hours"], 322)
		self.assertEqual(results[0]["completion_percentage"], 115)
		self.assertEqual(results[0]["user_totals"][self.fixture["owner_name"]]["completion_percentage"], 115)
		self.assertEqual(results[0]["status"], "warning")

	def test_fractional_percentages_keep_integer_threshold_semantics(self):
		positions = copy.deepcopy(self.positions)
		edited = next(row for row in positions if row["name"] == self.fixture["editing_position"])
		edited["details"][0]["hours"] = 39.72
		result = self.result("form", positions=positions)
		self.assertEqual(result["completion_percentage"], 114)
		self.assertEqual(result["display_completion_percentage"], 115)
		self.assertEqual(result["user_totals"][self.fixture["owner_name"]]["completion_percentage"], 115)

	def test_unsaved_overlay_is_counted_once_without_changing_saved_hours(self):
		positions = copy.deepcopy(self.positions)
		edited = next(row for row in positions if row["name"] == self.fixture["editing_position"])
		edited["details"][0]["hours"] = 48
		result = self.result("form", positions=positions)
		self.assertEqual(result["total_hours"], 330)
		self.assertEqual(result["hours_data"]["Editing"], 48)
		self.assertEqual(self.result("list")["total_hours"], 322)
		self.assertEqual(
			frappe.db.get_value("User Timesheet Position Details", {"parent": edited["name"]}, "hours"), 40
		)

	def test_required_and_optional_missing_plan_agree_through_both_aliases(self):
		for required, expected in ((True, "block"), (False, "no-plan")):
			set_limits_case(required=required, empty_plan=True)
			for alias in (calculate_timesheet_limits, calculate_user_timesheet_limits):
				for context in ("form", "list", "tree"):
					result = self.result(context, alias=alias)
					self.assertEqual(result["planned_hours"], 0)
					self.assertEqual(result["total_hours"], 322)
					self.assertEqual(result["status"], expected)
					self.assertEqual(result["plan_required"], required)

	def test_screenshot_percentages_are_rounded_without_changing_thresholds(self):
		plan = frappe.db.get_value(
			"Project Work Efforts",
			{"pwe_project": self.fixture["project"], "pwe_project_role": self.fixture["role"]},
			"name",
		)
		frappe.db.set_value(
			"Project Work Efforts Amount", {"parent": plan}, "pwea_plan", 1360, update_modified=False
		)
		positions = copy.deepcopy(self.positions)
		hours_by_name = {
			item["name"]: hours
			for item, hours in zip(self.fixture["positions"][:3], (80, 1128, 0), strict=True)
		}
		for row in positions:
			if row["name"] in hours_by_name:
				row["details"][0]["hours"] = hours_by_name[row["name"]]
		result = self.result("form", positions=positions)
		self.assertEqual(result["total_hours"], 1208)
		self.assertEqual(result["completion_percentage"], 88)
		self.assertEqual(result["display_completion_percentage"], 89)
		self.assertEqual(result["status_percentages"]["Approved"], 83)
		self.assertEqual(result["status_percentages"]["Pending Approval"], 6)
