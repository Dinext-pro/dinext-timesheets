import unittest
from unittest.mock import patch


class TestTimesheetWorkflowPermissions(unittest.TestCase):
	def test_timesheet_role_overrides_restore_read_only_base_once(self):
		from dinext_timesheets import workflow_permissions as permissions
		from dinext_common.workflow_approval import permissions as common_permissions

		frappe = permissions.frappe
		with (
			patch.dict(frappe.conf, {"enable_parallel_workflow_approval": 1}),
			patch.object(common_permissions, "supports_final_task_permission_queries", return_value=True),
			patch.object(frappe.db, "exists", return_value=True),
			patch.object(frappe.db, "get_value", side_effect=[None, frappe._dict(name="base", read=1, report=1)]),
			patch.object(frappe, "get_doc") as get_doc,
			patch.object(frappe, "clear_cache") as clear_cache,
		):
			permissions.restore_workflow_task_base_read()
			permissions.restore_workflow_task_base_read()

		get_doc.assert_called_once_with({
			"doctype": "Custom DocPerm", "parenttype": "DocType", "parentfield": "permissions",
			"parent": "Workflow Task", "role": "All", "permlevel": 0, "if_owner": 0, "read": 1, "report": 1,
		})
		get_doc.return_value.insert.assert_called_once_with(ignore_permissions=True)
		clear_cache.assert_called_once_with(doctype="Workflow Task")

	def test_existing_timesheet_base_read_recovers_standard_report_right(self):
		from dinext_timesheets import workflow_permissions as permissions
		from dinext_common.workflow_approval import permissions as common_permissions

		frappe = permissions.frappe
		with (
			patch.object(common_permissions, "supports_final_task_permission_queries", return_value=True),
			patch.object(frappe.db, "exists", return_value=True),
			patch.object(frappe.db, "get_value", return_value=frappe._dict(name="base", read=1, report=0)),
			patch.object(frappe.db, "set_value") as set_value,
			patch.object(frappe, "clear_cache") as clear_cache,
		):
			permissions.restore_workflow_task_base_read(during_cutover=True)

		set_value.assert_called_once_with("Custom DocPerm", "base", {"report": 1})
		clear_cache.assert_called_once_with(doctype="Workflow Task")

	def test_timesheet_role_overrides_are_retained_with_legacy_platform_or_engine(self):
		from dinext_timesheets import workflow_permissions as permissions
		from dinext_common.workflow_approval import permissions as common_permissions

		frappe = permissions.frappe
		with (
			patch.dict(frappe.conf, {"enable_parallel_workflow_approval": 0}),
			patch.object(common_permissions, "supports_final_task_permission_queries", return_value=False),
			patch.object(frappe.db, "exists") as exists,
		):
			permissions.restore_workflow_task_base_read()
			permissions.restore_workflow_task_base_read(during_cutover=True)
		exists.assert_not_called()


class TestLegacyTimesheetWorkflowRoutes(unittest.TestCase):
	def test_legacy_routes_use_the_owner_whitelist_and_http_methods(self):
		import frappe

		from dinext_timesheets import hooks, workflow_approval

		registered = {
			original: [override] for original, override in hooks.override_whitelisted_methods.items()
		}
		prefix = "dinext_common.workflow_approval.scenarios.timesheet_actions"
		targets = {
			"get_timesheet_position_actions": workflow_approval.get_timesheet_position_actions,
			"apply_timesheet_position_action": workflow_approval.apply_timesheet_position_action,
		}
		with (
			patch.object(frappe, "get_hooks", return_value=registered),
			patch.object(frappe, "get_installed_apps", return_value=["dinext_timesheets"]),
		):
			for name, handler in targets.items():
				with self.subTest(name=name):
					method = frappe.override_whitelisted_method(f"{prefix}.{name}")
					self.assertEqual(method, f"dinext_timesheets.workflow_approval.{name}")
					self.assertIs(frappe.get_attr(method), handler)
					self.assertIn(handler, frappe.whitelisted)
					self.assertNotIn(handler, frappe.guest_methods)
		self.assertEqual(
			frappe.allowed_http_methods_for_whitelisted_func[targets["apply_timesheet_position_action"]],
			["POST"],
		)
