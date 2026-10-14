# Copyright (c) 2026, Dinext and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from dinext_timesheets.workflow_approval import _save_system_task


class TestSystemTaskSave(FrappeTestCase):
	def test_actual_date_save_runs_as_administrator(self):
		seen = {}

		class Task:
			def save(self, ignore_permissions=False):
				seen["user"] = frappe.session.user
				seen["ignore_permissions"] = ignore_permissions

		approver = "wf.approver2@example.com"
		frappe.set_user(approver)
		_save_system_task(Task())
		self.assertEqual(seen["user"], "Administrator")
		self.assertTrue(seen["ignore_permissions"])
		self.assertEqual(frappe.session.user, approver)
