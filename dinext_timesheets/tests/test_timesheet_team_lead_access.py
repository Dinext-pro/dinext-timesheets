from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from dinext_timesheets.dinext_timesheets.user_timesheet import permissions


class TestTimesheetTeamLeadAccess(FrappeTestCase):
	def setUp(self):
		self.token = frappe.generate_hash(length=10)
		self.worker = f"worker-{self.token}@example.com"
		self.previous = f"previous-{self.token}@example.com"
		self.lead = f"lead-{self.token}@example.com"
		self.next_lead = f"next-{self.token}@example.com"
		self.group = f"team-{self.token}"
		self.other_group = f"other-{self.token}"
		frappe.db.savepoint("teamlead_" + self.token)
		self.addCleanup(frappe.db.rollback, save_point="teamlead_" + self.token)
		self._insert("Worker", "worker-" + self.token, wuser=self.worker, wuser_group=self.group)
		self._assignment(self.group, self.previous, "2039-01-01", 1)
		self._assignment(self.group, self.previous, "2039-01-07", 2)
		self._assignment(self.group, self.lead, "2039-01-07", 3)
		self._assignment(self.group, self.next_lead, "2039-01-08", 4)
		self._assignment(self.other_group, self.next_lead, "2039-01-07", 1)

	def _insert(self, doctype, name, **fields):
		frappe.get_doc({"doctype": doctype, "name": name, **fields}).db_insert()

	def _assignment(self, group, user, date, idx):
		self._insert(
			"Teamleads Table",
			frappe.generate_hash(length=10),
			parent=group,
			parenttype="User Group",
			parentfield="custom_table",
			teamlead=user,
			date=date,
			idx=idx,
		)

	def test_scope_uses_inclusive_end_and_latest_row_on_same_date(self):
		for actor, permitted in (
			(self.worker, True),
			(self.lead, True),
			(self.previous, False),
			(self.next_lead, False),
		):
			with self.subTest(actor=actor):
				self.assertEqual(
					permissions.has_worker_scope(self.worker, "2039-01-07", actor), permitted
				)
		self.assertTrue(permissions.has_worker_scope(self.worker, "2039-01-06", self.previous))

	def test_scope_does_not_replace_configured_create_permission(self):
		with patch.object(frappe, "has_permission", return_value=False):
			with self.assertRaises(frappe.PermissionError):
				permissions.assert_can_create_for_worker(self.worker, "2039-01-07", self.lead)
		with patch.object(frappe, "has_permission", return_value=True):
			permissions.assert_can_create_for_worker(self.worker, "2039-01-07", self.lead)
			with self.assertRaises(frappe.PermissionError):
				permissions.assert_can_create_for_worker(self.worker, "2039-01-07", self.previous)


class TestDelegatedTimesheetWorkflow(FrappeTestCase):
	def test_document_permissions_and_position_workflow(self):
		from dinext_timesheets.tests.timesheet_team_lead_ui import seed
		from dinext_timesheets.workflow_approval import (
			apply_timesheet_position_action,
			get_timesheet_position_actions,
		)

		caller = frappe.session.user
		frappe.db.savepoint("delegated_timesheet")
		self.addCleanup(frappe.clear_document_cache, "Workflow")
		self.addCleanup(frappe.clear_document_cache, "Server Script")
		self.addCleanup(frappe.db.rollback, save_point="delegated_timesheet")
		self.addCleanup(frappe.set_user, caller)
		fixture = seed()
		payload = {
			"doctype": "User Timesheet",
			"timesheet_from": fixture["worker"],
			"timesheet_from_name": "Delegated server test",
			"ts_valid_from": fixture["start"],
			"ts_valid_for": fixture["end"],
			"user_group": "Forged group",
		}
		frappe.set_user(fixture["former"])
		with self.assertRaises(frappe.PermissionError):
			frappe.get_doc(payload).insert()

		frappe.set_user(caller)
		role_name = f"Test timesheet delegation {frappe.generate_hash(length=8)}"
		frappe.get_doc({"doctype": "Role", "role_name": role_name, "desk_access": 1}).insert()
		grant = frappe.get_doc("Custom DocPerm", "ut-team-lead-access")
		custom_grant = frappe.copy_doc(grant)
		custom_grant.role = role_name
		custom_grant.name = frappe.generate_hash(length=10)
		custom_grant.db_insert()
		for name in ("UT_Permissions-1", "UTP_Permissions-1"):
			config = frappe.get_doc("DocType Permission", name)
			rule = next(row for row in config.conditions if row.role == grant.role)
			custom_rule = frappe.copy_doc(rule)
			custom_rule.role = role_name
			custom_rule.name = frappe.generate_hash(length=10)
			custom_rule.db_insert()
		frappe.db.delete("Has Role", {"parent": fixture["lead"], "role": grant.role})
		frappe.clear_cache(user=fixture["lead"])
		frappe.clear_cache(doctype="User Timesheet")
		frappe.clear_cache(doctype="User Timesheet Position")
		frappe.set_user(fixture["lead"])
		with self.assertRaises(frappe.PermissionError):
			frappe.get_doc(payload).insert()

		frappe.set_user(caller)
		user = frappe.get_doc("User", fixture["lead"])
		user.add_roles(role_name)
		frappe.set_user(fixture["lead"])
		parent = frappe.get_doc(payload).insert()
		self.assertEqual(parent.timesheet_from, fixture["worker"])
		self.assertNotEqual(parent.user_group, payload["user_group"])
		self.assertEqual(parent.owner, fixture["lead"])
		positions = [
			frappe.get_doc({
				"doctype": "User Timesheet Position", "user_timesheet": parent.name,
				"project": fixture["project"], "project_role": fixture["role"],
				"document_type": "Task", "document_name": task,
				"table": [{"date": fixture["start"], "hours": 1, "description": "Reported work"}],
			}).insert()
			for task in fixture["tasks"]
		]
		self.assertTrue(all(row.user == fixture["worker"] for row in positions))
		frappe.set_user(fixture["former"])
		self.assertFalse(frappe.get_list("User Timesheet", filters={"name": parent.name}))
		self.assertFalse(frappe.get_list("User Timesheet Position", filters={"user_timesheet": parent.name}))
		self.assertFalse(frappe.has_permission(positions[0], "read"))
		with self.assertRaises(frappe.PermissionError):
			get_timesheet_position_actions(parent.name)
		with self.assertRaises(frappe.PermissionError):
			apply_timesheet_position_action(parent.name, fixture["actions"]["submit"])

		frappe.set_user(fixture["worker"])
		self.assertTrue(frappe.has_permission(parent, "read"))
		frappe.set_user(fixture["lead"])
		self.assertTrue(frappe.has_permission(parent, "read"))
		self.assertEqual(len(frappe.get_list("User Timesheet Position", filters={"user_timesheet": parent.name})), 2)
		apply_timesheet_position_action(parent.name, fixture["actions"]["submit"])
		self.assertEqual(parent.reload().ut_status, "Pending Approval")
		locked = positions[0].reload()
		locked.table[0].description = "Attempt to edit during approval"
		with self.assertRaises(frappe.PermissionError):
			locked.save()
		self.assertEqual(locked.reload().table[0].description, "Reported work")
		available = get_timesheet_position_actions(parent.name)["actions"]
		self.assertNotIn(fixture["actions"]["approve"], [row["action"] for row in available])
		with self.assertRaises(frappe.ValidationError):
			apply_timesheet_position_action(parent.name, fixture["actions"]["approve"])
		apply_timesheet_position_action(parent.name, fixture["actions"]["withdraw"])
		self.assertEqual(parent.reload().ut_status, "Rework")
		self.assertFalse(frappe.db.exists("Workflow Task", {
			"reference_doctype": "User Timesheet Position",
			"reference_name": ("in", [row.name for row in positions]),
			"workflow_state": "Pending Approval",
			"round_status": "Open",
		}))
		apply_timesheet_position_action(parent.name, fixture["actions"]["submit"])
		frappe.set_user(fixture["approver"])
		apply_timesheet_position_action(parent.name, fixture["actions"]["reject"], comment="Needs detail")
		self.assertEqual(parent.reload().ut_status, "Rejected")

		frappe.set_user(fixture["lead"])
		self.assertTrue(any(row.reload().reject_reason == "Needs detail" for row in positions))
		apply_timesheet_position_action(parent.name, fixture["actions"]["revise"])
		self.assertEqual(parent.reload().ut_status, "Rework")
		positions[0].reload().table[0].description = "Added detail"
		positions[0].save()
		apply_timesheet_position_action(parent.name, fixture["actions"]["submit"])
		frappe.set_user(fixture["approver"])
		result = apply_timesheet_position_action(parent.name, fixture["actions"]["approve"])
		self.assertEqual(parent.reload().ut_status, "Approved", result["messages"])
		frappe.set_user(fixture["lead"])
		self.assertTrue(frappe.has_permission(parent, "read"))
		apply_timesheet_position_action(parent.name, fixture["actions"]["reopen"])
		self.assertEqual(parent.reload().ut_status, "Rework")
