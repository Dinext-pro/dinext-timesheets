import unittest
from unittest.mock import Mock, patch

from dinext_timesheets import workflow_deadlines


class TestWorkflowApproverGroups(unittest.TestCase):
	def test_provider_uses_current_users_worker_permissions(self):
		frappe = Mock()
		frappe.get_list.return_value = [
			{"wuser": "visible@example.com", "wuser_group": "Visible Group"},
			{"wuser": "no-group@example.com"},
		]
		approvers = ("visible@example.com", "unreadable@example.com", "no-group@example.com")
		with patch.object(workflow_deadlines, "frappe", frappe):
			self.assertEqual(workflow_deadlines.approver_groups(approvers), {"visible@example.com": "Visible Group"})

		frappe.has_permission.assert_called_once_with("Worker", "read")
		frappe.get_list.assert_called_once_with(
			"Worker",
			filters={"wuser": ["in", approvers]},
			fields=["wuser", "wuser_group"],
			limit_page_length=0,
		)

	def test_provider_does_not_read_worker_rows_without_permission(self):
		frappe = Mock()
		frappe.has_permission.return_value = False
		with patch.object(workflow_deadlines, "frappe", frappe):
			self.assertEqual(workflow_deadlines.approver_groups(("unreadable@example.com",)), {})

		frappe.get_list.assert_not_called()
