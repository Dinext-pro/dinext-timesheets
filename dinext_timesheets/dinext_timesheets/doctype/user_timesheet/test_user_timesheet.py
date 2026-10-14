# Copyright (c) 2026, Dinext and Contributors
# See license.txt

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from dinext_timesheets import workflow_approval


class TestUserTimesheet(FrappeTestCase):
	def test_app_owned_clients_do_not_call_bare_timesheet_status_api(self):
		public_js = Path(frappe.get_app_path("dinext_timesheets", "public", "js"))
		ut = public_js / "user_timesheet"
		submit_source = (ut / "submit.js").read_text()
		workflow_source = (ut / "workflow.js").read_text()
		dashboard_source = (ut / "dashboard.js").read_text()
		columns_source = (ut / "columns.js").read_text()
		limits_source = (ut / "limits.js").read_text()
		list_source = (public_js / "user_timesheet_position_list.js").read_text()
		combined = submit_source + workflow_source + dashboard_source + list_source
		self.assertIn(
			"dinext_timesheets.workflow_approval.orchestrate_timesheet",
			submit_source,
		)
		self.assertIn(
			"dinext_timesheets.workflow_approval.vote_timesheet_positions",
			workflow_source,
		)
		self.assertIn("row.transitioned", workflow_source)
		self.assertIn("guardEditableTimesheet", workflow_source)
		self.assertNotIn("add_custom_button(__(BTN_STOP)", submit_source)
		self.assertIn("frm._ut_wf_button_labels", submit_source)
		chrome_source = (ut / "form_chrome.js").read_text()
		workflow_at = chrome_source.index("await processUTWorkflow(frm)")
		submit_at = chrome_source.index("setupSubmitButtons(frm)")
		self.assertLess(workflow_at, submit_at)
		self.assertIn(
			"dinext_common.workflow_approval.api.get_pending_approvers",
			dashboard_source,
		)
		self.assertIn("Action expected from: {0}", dashboard_source)
		self.assertIn("reference_name", dashboard_source)
		self.assertIn("approver_tooltip", dashboard_source)
		self.assertIn(
			"uniqueApproverNames(byPosition.get(String(gridRow.id)) || [], true)",
			dashboard_source,
		)
		self.assertNotIn("get_pending_approver_names", dashboard_source)
		self.assertNotIn("position(s)", dashboard_source)
		self.assertNotIn("get_form_link", dashboard_source)
		self.assertIn("approver_tooltip", columns_source)
		self.assertIn("tooltipValueGetter: invalidTooltip", columns_source)
		self.assertNotIn("get_common_transition_actions", workflow_source)
		self.assertIn(
			"dinext_common.workflow_approval.api.bulk_vote",
			list_source,
		)
		self.assertNotIn('method: "set_timesheet_status"', combined)
		self.assertNotIn("method: 'set_timesheet_status'", combined)
		self.assertNotIn("window[name]", list_source)
		self.assertIn("export async function checkLimits", limits_source)
		self.assertIn("export async function showTaskPlanFact", limits_source)

	def test_replaced_client_scripts_are_not_retained_as_async_loaders(self):
		app_path = Path(frappe.get_app_path("dinext_timesheets"))
		fixtures = json.loads(
			(app_path / "fixtures" / "client_script.json").read_text()
		)
		names = {row["name"] for row in fixtures}
		self.assertNotIn("Custom_ListView_6", names)
		self.assertNotIn(
			"User_Timesheet_Position_to_User_Timesheet_form_integration_V10",
			names,
		)
		for removed in (
			"Множественное_Согласование_AFL_V3",
			"WT_To_UTP_Route",
			"UT_Accept_WF",
			"UTP_History_Data",
			"UTP_Route",
			"UTP_ListView_Style_2",
		):
			self.assertNotIn(removed, names)
		hooks = (app_path / "hooks.py").read_text()
		self.assertIn("public/js/user_timesheet_position_form.js", hooks)
		server_scripts = {
			row["name"]
			for row in json.loads((app_path / "fixtures" / "server_script.json").read_text())
		}
		for removed in (
			"AFL WT After Save",
			"AFL WT Before Save",
			"AFL_Deleted_WTs_Deleted",
			"UTP Check WT Before Save V2",
			"UTP Proccess WT After Save",
			"UTP_Deleted_WTs_Deleted",
			"Set Timesheet Status",
			"UTP_UT_Status_V3",
			"Task Limit Exceeded_V4",
		):
			self.assertNotIn(removed, server_scripts)
		self.assertIn('"public/js/user_timesheet/entry.js"', hooks)
		self.assertNotIn("user_timesheet_form.js", hooks)
		self.assertNotIn("user_timesheet_approvals.js", hooks)

	def test_zero_positions_do_not_require_daily_hours(self):
		parent = SimpleNamespace(
			name="UT-1",
			timesheet_from="owner@example.com",
			ts_valid_from="2026-09-01",
			ts_valid_for="2026-09-07",
		)
		with (
			patch.object(workflow_approval, "_validate_parent_period", return_value=[]),
			patch.object(
				workflow_approval,
				"_calendar_context",
				side_effect=AssertionError("calendar validation must be skipped"),
			),
		):
			workflow_approval._validate_positions(parent, [])

	def test_zero_position_operations_use_exact_parent_states(self):
		self.assertEqual(
			workflow_approval._operation_states("Start", has_positions=False),
			(workflow_approval.PARENT_APPROVED, None),
		)
		self.assertEqual(
			workflow_approval._operation_states("Stop", has_positions=False),
			(workflow_approval.PARENT_APPROVED, None),
		)
		self.assertEqual(
			workflow_approval._operation_states("Edit", has_positions=False),
			(workflow_approval.REWORK, None),
		)

	def test_stop_is_owner_only_even_for_system_manager(self):
		parent = SimpleNamespace(
			timesheet_from="owner@example.com",
			ut_status=workflow_approval.PENDING,
			user_group="Team",
			ts_valid_from="2026-09-01",
		)
		with patch.object(frappe, "get_roles", return_value=["System Manager"]):
			with self.assertRaises(frappe.PermissionError):
				workflow_approval._authorize_operation(
					parent,
					"Stop",
					actor="manager@example.com",
				)

	def test_latest_dated_team_lead_can_start(self):
		parent = SimpleNamespace(
			timesheet_from="owner@example.com",
			ut_status=workflow_approval.REWORK,
			user_group="Team",
			ts_valid_from="2026-09-01",
		)
		with (
			patch.object(frappe, "get_roles", return_value=["Dinext_Team_Lead"]),
			patch.object(
				workflow_approval,
				"_current_team_lead",
				return_value="lead@example.com",
			),
		):
			workflow_approval._authorize_operation(
				parent,
				"Start",
				actor="lead@example.com",
			)

	def test_position_shape_validation_rejects_integration_v10_errors(self):
		parent = SimpleNamespace(
			name="UT-1",
			timesheet_from="owner@example.com",
			ts_valid_from="2026-09-01",
			ts_valid_for="2026-09-07",
		)
		invalid = SimpleNamespace(
			name="UTP-1",
			user_timesheet="UT-1",
			user="owner@example.com",
			project=None,
			document_type=None,
			document_name=None,
			project_role=None,
			all_hours=0,
			table=[
				SimpleNamespace(
					date="2026-09-07",
					hours=0,
					description="",
				),
				SimpleNamespace(
					date="2026-09-08",
					hours=1,
					description="",
				)
			],
		)
		errors = workflow_approval._validate_position_shape(
			parent,
			invalid,
			description_required=True,
		)
		self.assertTrue(any("project" in error.lower() for error in errors))
		self.assertTrue(any("task" in error.lower() for error in errors))
		self.assertTrue(any("role" in error.lower() for error in errors))
		self.assertTrue(any("positive" in error.lower() for error in errors))
		self.assertTrue(any("description" in error.lower() for error in errors))
		self.assertTrue(any("outside" in error.lower() for error in errors))

	def test_daily_validation_combines_leave_and_reduced_hours(self):
		parent = SimpleNamespace(ts_valid_from="2026-09-01", ts_valid_for="2026-09-02")
		template = SimpleNamespace(hours_on_date=8, minimum_hours=0, maximum_hours=0)
		positions = [
			SimpleNamespace(
				table=[
					SimpleNamespace(date="2026-09-01", hours=4),
					SimpleNamespace(date="2026-09-02", hours=99),
				]
			)
		]
		errors = workflow_approval._validate_daily_totals(
			parent,
			positions,
			template,
			holidays={frappe.utils.getdate("2026-09-02")},
			reduced={frappe.utils.getdate("2026-09-01"): 6},
			leave_hours={frappe.utils.getdate("2026-09-01"): 2},
		)
		self.assertEqual(errors, [])

	def test_required_planned_hours_fail_closed(self):
		parent = SimpleNamespace(name="UT-1")
		position = SimpleNamespace(
			project="PROJ-1",
			document_type="Task",
			document_name="TASK-1",
			project_role="Developer",
			table=[],
		)

		def get_value(_doctype, _name, fieldname=None, **_kwargs):
			if fieldname == "custom_обязательность_плановых_трудозатрат":
				return "Обязательно для всех Задач"
			return None

		with (
			patch.object(frappe.db, "get_value", side_effect=get_value),
			patch.object(workflow_approval, "_find_plan", return_value=None),
			patch.object(workflow_approval, "_root_task_with_issue", return_value=None),
		):
			errors = workflow_approval._validate_planned_limits(parent, [position])
		self.assertEqual(len(errors), 1)
		self.assertIn("planned hours", errors[0].lower())

	def test_positions_are_locked_in_stable_name_order(self):
		parent = SimpleNamespace(
			name="UT-1",
			timesheet_from="owner@example.com",
			user_group="Team",
		)
		lock_order = []

		class FakePosition:
			def __init__(self, name):
				self.name = name
				self.table = []

			def update(self, values):
				for key, value in values.items():
					setattr(self, key, value)

			def set(self, fieldname, rows):
				setattr(
					self,
					fieldname,
					[SimpleNamespace(**row) for row in rows],
				)

		def get_doc(_doctype, name, *, for_update=False):
			self.assertTrue(for_update)
			lock_order.append(name)
			return FakePosition(name)

		payloads = [
			{"name": "UTP-2", "table": []},
			{"name": "UTP-1", "table": []},
		]
		with (
			patch.object(frappe, "get_all", return_value=["UTP-2", "UTP-1"]),
			patch.object(frappe, "get_doc", side_effect=get_doc),
		):
			workflow_approval._prepare_positions(parent, payloads, [])
		self.assertEqual(lock_order, ["UTP-1", "UTP-2"])

	def test_every_retained_position_must_be_in_payload(self):
		parent = SimpleNamespace(name="UT-1")
		with (
			patch.object(frappe, "get_all", return_value=["UTP-1"]),
			patch.object(
				frappe,
				"get_doc",
				return_value=SimpleNamespace(name="UTP-1"),
			),
			self.assertRaises(frappe.ValidationError),
		):
			workflow_approval._prepare_positions(parent, [], [])

	def test_parent_status_stays_when_sibling_transition_fails(self):
		parent = SimpleNamespace(
			name="UT-1",
			ut_status=workflow_approval.PENDING,
			save=Mock(),
		)
		changed = SimpleNamespace(name="UTP-1", status=workflow_approval.EDITING)
		frappe.flags.timesheet_transition_messages = []

		def fail_sibling(*_args, **_kwargs):
			raise frappe.ValidationError("sibling failed")

		with (
			patch.object(
				workflow_approval,
				"load_position_statuses",
				return_value=[workflow_approval.EDITING],
			),
			patch(
				"dinext_timesheets.timesheet_settings._settings_doc",
				return_value=None,
			),
			patch(
				"dinext_timesheets.timesheet_settings.position_workflow_states",
				return_value=["Editing", "Pending Approval", "Approved", "Rejected"],
			),
			patch.object(frappe, "get_all", return_value=["UTP-2"]),
			patch.object(frappe, "log_error"),
			patch(
				"dinext_common.workflow_approval.engine.apply_domain_transition",
				side_effect=fail_sibling,
			),
		):
			workflow_approval._recalculate_parent(
				parent,
				changed,
				workflow_approval.PENDING,
			)

		self.assertEqual(parent.ut_status, workflow_approval.REWORK)
		parent.save.assert_called_once()
		self.assertEqual(len(frappe.flags.timesheet_transition_messages), 1)
		self.assertIn("UTP-2", frappe.flags.timesheet_transition_messages[0])

	def test_open_round_does_not_change_the_parent(self):
		doc = SimpleNamespace(
			status=workflow_approval.EDITING,
			document_type="Task",
			document_name="TASK-1",
			user_timesheet="UT-1",
			get_doc_before_save=lambda: SimpleNamespace(status=workflow_approval.EDITING),
		)
		with (
			patch.object(workflow_approval, "_enabled", return_value=True),
			patch.object(frappe, "get_doc") as get_doc,
		):
			workflow_approval.on_utp_update(doc)
		get_doc.assert_not_called()

	def test_applied_transition_sets_parent_without_moving_siblings(self):
		parent = SimpleNamespace(
			name="UT-1",
			ut_status=workflow_approval.REWORK,
			ut_approval_date="2026-10-01",
			save=Mock(),
		)
		changed = SimpleNamespace(name="UTP-1", status=workflow_approval.PENDING)
		with (
			patch.object(
				workflow_approval,
				"load_position_statuses",
				return_value=[workflow_approval.PENDING],
			),
			patch(
				"dinext_timesheets.timesheet_settings._settings_doc",
				return_value=None,
			),
			patch(
				"dinext_timesheets.timesheet_settings.position_workflow_states",
				return_value=["Editing", "Pending Approval", "Approved", "Rejected"],
			),
			patch(
				"dinext_common.workflow_approval.engine.apply_domain_transition"
			) as transition,
		):
			workflow_approval._recalculate_parent(
				parent,
				changed,
				workflow_approval.EDITING,
			)
		self.assertEqual(parent.ut_status, workflow_approval.PENDING)
		self.assertIsNone(parent.ut_approval_date)
		parent.save.assert_called_once()
		transition.assert_not_called()

	def test_pending_parent_waits_while_a_position_is_still_editing(self):
		parent = SimpleNamespace(
			name="UT-1",
			ut_status=workflow_approval.REWORK,
			ut_approval_date=None,
			save=Mock(),
		)
		changed = SimpleNamespace(name="UTP-1", status=workflow_approval.PENDING)
		with (
			patch.object(
				workflow_approval,
				"load_position_statuses",
				return_value=[workflow_approval.PENDING, workflow_approval.EDITING],
			),
			patch(
				"dinext_timesheets.timesheet_settings._settings_doc",
				return_value=None,
			),
			patch(
				"dinext_timesheets.timesheet_settings.position_workflow_states",
				return_value=["Editing", "Pending Approval", "Approved", "Rejected"],
			),
			patch(
				"dinext_common.workflow_approval.engine.apply_domain_transition"
			) as transition,
		):
			workflow_approval._recalculate_parent(
				parent,
				changed,
				workflow_approval.EDITING,
			)
		self.assertEqual(parent.ut_status, workflow_approval.REWORK)
		parent.save.assert_not_called()
		transition.assert_not_called()

	def test_later_vote_conflict_keeps_the_applied_transition(self):
		from dinext_common.workflow_approval.engine import WorkflowApprovalConflictError

		parent = SimpleNamespace(name="UT-1", check_permission=Mock())

		def task_row(position):
			return frappe._dict(
				status="Working",
				round_status="Open",
				reference_doctype="User Timesheet Position",
				reference_name=position,
				workflow_state=workflow_approval.PENDING,
			)

		def get_value(doctype, name, fieldname=None, **_kwargs):
			if doctype == "Workflow Task":
				return task_row("UTP-1" if name == "T1" else "UTP-2")
			if doctype == "User Timesheet Position":
				return workflow_approval.PENDING
			return None

		def vote(task_name, **_kwargs):
			if task_name == "T2":
				raise WorkflowApprovalConflictError(
					"The source workflow state has changed"
				)
			return {
				"task": task_name,
				"transitioned": True,
				"round_status": "Transitioned",
			}

		with (
			patch.object(frappe, "get_doc", return_value=parent),
			patch.object(
				workflow_approval,
				"get_timesheet_approval_actions",
				return_value={
					"tasks": ["T1", "T2"],
					"actions": [{"action": "Stop"}],
				},
			),
			patch.object(frappe.db, "get_value", side_effect=get_value),
			patch(
				"frappe.model.workflow.get_workflow",
				return_value=SimpleNamespace(workflow_state_field="workflow_state"),
			),
			patch(
				"dinext_common.workflow_approval.engine.cast_vote",
				side_effect=vote,
			),
		):
			result = workflow_approval.vote_timesheet_positions("UT-1", "Stop")

		self.assertEqual(result["results"], [vote("T1")])
		self.assertTrue(result["messages"])

	def test_first_vote_conflict_still_reaches_the_caller(self):
		from dinext_common.workflow_approval.engine import WorkflowApprovalConflictError

		parent = SimpleNamespace(name="UT-1", check_permission=Mock())

		def get_value(doctype, name, fieldname=None, **_kwargs):
			if doctype == "Workflow Task":
				return frappe._dict(
					status="Working",
					round_status="Open",
					reference_doctype="User Timesheet Position",
					reference_name="UTP-1",
					workflow_state=workflow_approval.PENDING,
				)
			return workflow_approval.PENDING

		def vote(*_args, **_kwargs):
			raise WorkflowApprovalConflictError("The source workflow state has changed")

		with (
			patch.object(frappe, "get_doc", return_value=parent),
			patch.object(
				workflow_approval,
				"get_timesheet_approval_actions",
				return_value={"tasks": ["T1"], "actions": [{"action": "Stop"}]},
			),
			patch.object(frappe.db, "get_value", side_effect=get_value),
			patch(
				"frappe.model.workflow.get_workflow",
				return_value=SimpleNamespace(workflow_state_field="workflow_state"),
			),
			patch(
				"dinext_common.workflow_approval.engine.cast_vote",
				side_effect=vote,
			),
			self.assertRaises(WorkflowApprovalConflictError),
		):
			workflow_approval.vote_timesheet_positions("UT-1", "Stop")

	def test_moved_position_is_not_voted_again(self):
		parent = SimpleNamespace(name="UT-1", check_permission=Mock())

		def get_value(doctype, name, fieldname=None, **_kwargs):
			if doctype == "Workflow Task":
				return frappe._dict(
					status="Working",
					round_status="Open",
					reference_doctype="User Timesheet Position",
					reference_name="UTP-1",
					workflow_state=workflow_approval.PENDING,
				)
			return workflow_approval.EDITING

		with (
			patch.object(frappe, "get_doc", return_value=parent),
			patch.object(
				workflow_approval,
				"get_timesheet_approval_actions",
				return_value={"tasks": ["T1"], "actions": [{"action": "Stop"}]},
			),
			patch.object(frappe.db, "get_value", side_effect=get_value),
			patch(
				"frappe.model.workflow.get_workflow",
				return_value=SimpleNamespace(workflow_state_field="workflow_state"),
			),
			patch("dinext_common.workflow_approval.engine.cast_vote") as vote,
		):
			result = workflow_approval.vote_timesheet_positions("UT-1", "Stop")

		vote.assert_not_called()
		self.assertEqual(result["results"], [])

	def test_orchestrator_validates_before_persistent_side_effects(self):
		parent = SimpleNamespace(
			name="UT-1",
			ut_status=workflow_approval.DRAFT,
			ut_approval_date=None,
			reload=Mock(),
			save=Mock(),
		)
		position = SimpleNamespace(name="UTP-1", save=Mock(), insert=Mock())
		deleted = SimpleNamespace(name="UTP-2", delete=Mock())
		with (
			patch.object(frappe, "get_doc", return_value=parent),
			patch.object(workflow_approval, "_authorize_operation"),
			patch.object(workflow_approval, "_parse_positions", return_value=[]),
			patch.object(workflow_approval, "_parse_names", return_value=[]),
			patch.object(
				workflow_approval,
				"_prepare_positions",
				return_value=([position], [deleted]),
			),
			patch.object(
				workflow_approval,
				"_validate_positions",
				side_effect=frappe.ValidationError("invalid middle row"),
			),
			self.assertRaises(frappe.ValidationError),
		):
			workflow_approval.orchestrate_timesheet("UT-1", "Start")
		position.save.assert_not_called()
		position.insert.assert_not_called()
		deleted.delete.assert_not_called()
		parent.save.assert_not_called()

	def test_zero_position_orchestration_has_exact_parent_states(self):
		expected_states = {
			"Start": workflow_approval.PARENT_APPROVED,
			"Stop": workflow_approval.PARENT_APPROVED,
			"Edit": workflow_approval.REWORK,
		}
		for operation, expected_state in expected_states.items():
			with self.subTest(operation=operation):
				parent = SimpleNamespace(
					name="UT-1",
					ut_status=workflow_approval.DRAFT,
					ut_approval_date=None,
					reload=Mock(),
					save=Mock(),
				)
				with (
					patch.object(frappe, "get_doc", return_value=parent),
					patch.object(workflow_approval, "_authorize_operation"),
					patch.object(workflow_approval, "_parse_positions", return_value=[]),
					patch.object(workflow_approval, "_parse_names", return_value=[]),
					patch.object(
						workflow_approval,
						"_prepare_positions",
						return_value=([], []),
					),
					patch.object(workflow_approval, "_validate_positions"),
					patch(
						"dinext_common.workflow_approval.engine.apply_domain_transition"
					) as transition,
				):
					result = workflow_approval.orchestrate_timesheet(
						"UT-1",
						operation,
					)
				transition.assert_not_called()
				self.assertEqual(parent.ut_status, expected_state)
				self.assertEqual(result["processed"], 0)

	def test_system_manager_uses_workflow_selected_domain_actor(self):
		with patch.object(
			frappe,
			"get_roles",
			return_value=["System Manager"],
		):
			self.assertIsNone(
				workflow_approval._domain_transition_actor("manager@example.com")
			)

	def test_automatic_child_approvals_preserve_approved_parent(self):
		parent = SimpleNamespace(
			name="UT-1",
			ut_status=workflow_approval.DRAFT,
			ut_approval_date=None,
			reload=Mock(),
			save=Mock(),
		)
		position = SimpleNamespace(
			name="UTP-1",
			is_new=lambda: False,
			save=Mock(),
		)
		with (
			patch.object(frappe, "get_doc", return_value=parent),
			patch.object(workflow_approval, "_authorize_operation"),
			patch.object(workflow_approval, "_parse_positions", return_value=[]),
			patch.object(workflow_approval, "_parse_names", return_value=[]),
			patch.object(
				workflow_approval,
				"_prepare_positions",
				return_value=([position], []),
			),
			patch.object(workflow_approval, "_validate_positions"),
			patch.object(workflow_approval, "_domain_transition_actor", return_value=None),
			patch.object(frappe.db, "count", return_value=0),
			patch(
				"dinext_common.workflow_approval.engine.apply_domain_transition"
			),
		):
			result = workflow_approval.orchestrate_timesheet("UT-1", "Start")
		self.assertEqual(parent.ut_status, workflow_approval.PARENT_APPROVED)
		self.assertEqual(result["status"], workflow_approval.PARENT_APPROVED)

	def test_issue_hours_count_toward_blocking_plan_limit(self):
		parent = SimpleNamespace(name="UT-1")
		position = SimpleNamespace(
			document_type="Issue",
			document_name="ISSUE-1",
			project="PROJ-1",
			project_role="Developer",
			table=[SimpleNamespace(hours=6)],
		)

		def get_value(doctype, name_or_filters, fieldname=None, **_kwargs):
			if doctype == "Task" and isinstance(name_or_filters, dict):
				return "TASK-1"
			if doctype == "Project":
				return "Опционально"
			if doctype == "Limit Control":
				return 100
			return None

		def get_all(doctype, **_kwargs):
			if doctype == "Task":
				return ["ISSUE-1"]
			return []

		with (
			patch.object(frappe.db, "get_value", side_effect=get_value),
			patch.object(frappe, "get_all", side_effect=get_all),
			patch.object(
				workflow_approval,
				"_find_plan",
				return_value=("TASK-1", 5),
			),
			patch.object(workflow_approval, "_task_children", return_value=[]),
		):
			errors = workflow_approval._validate_planned_limits(parent, [position])
		self.assertEqual(len(errors), 1)
		self.assertIn("blocking", errors[0].lower())

	def test_excluded_task_is_rejected_server_side(self):
		parent = SimpleNamespace(
			timesheet_from="owner@example.com",
			ts_valid_from="2026-09-01",
			ts_valid_for="2026-09-07",
		)
		position = SimpleNamespace(
			name="UTP-1",
			project="PROJ-1",
			document_type="Task",
			document_name="TASK-1",
			project_role="Developer",
		)
		template = SimpleNamespace(
			doctype_for_timesheet=[SimpleNamespace(dtdoctype="Task")]
		)

		def get_value(doctype, name, _fields=None, **_kwargs):
			if doctype == "Project":
				return frappe._dict(
					name=name,
					status="Open",
					is_active="Yes",
					expected_start_date="2026-01-01",
					expected_end_date="2026-12-31",
				)
			if doctype == "Task":
				return frappe._dict(
					project="PROJ-1",
					custom_include=0,
					status="Open",
					is_milestone=0,
					exp_start_date="2026-01-01",
					exp_end_date="2026-12-31",
					completed_on=None,
				)
			return None

		with (
			patch.object(frappe.db, "get_value", side_effect=get_value),
			patch.object(frappe.db, "exists", return_value=True),
			patch.object(
				workflow_approval,
				"_participant_values",
				return_value={"owner@example.com"},
			),
			patch.object(
				frappe,
				"get_all",
				return_value=[
					SimpleNamespace(
						pt_valid_from="2026-01-01",
						pt_valid_for="2026-12-31",
					)
				],
			),
		):
			errors = workflow_approval._validate_position_links(
				parent,
				position,
				template,
			)
		self.assertTrue(any("excluded" in error.lower() for error in errors))

	def test_calendar_requires_holiday_list(self):
		parent = SimpleNamespace(
			timesheet_from="owner@example.com",
			ts_valid_from="2026-09-01",
			ts_valid_for="2026-09-07",
		)
		worker = SimpleNamespace(
			wtimesheet_template="TEMPLATE-1",
			wholiday_list=None,
		)
		template = SimpleNamespace(tt_working_hours_on_date=None)
		with (
			patch.object(frappe.db, "get_value", return_value="WORKER-1"),
			patch.object(
				frappe,
				"get_doc",
				side_effect=[worker, template],
			),
			self.assertRaises(frappe.ValidationError),
		):
			workflow_approval._calendar_context(parent)
