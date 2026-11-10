"""Use stored Timesheet entries, including fractions and empty comments."""

import frappe
from frappe.tests.utils import FrappeTestCase


class TestWorkflowEmailDetails(FrappeTestCase):
	def test_adapter_supplies_stored_entries_in_child_order(self):
		from dinext_timesheets.workflow_email import digest_item, email_context

		frappe.set_user("Administrator")
		marker = "mail-details-" + frappe.generate_hash(length=10)
		user = frappe.get_doc(
			dict(
				doctype="User",
				email=marker + "@example.test",
				first_name="Иван",
				last_name="Петров",
				send_welcome_email=0,
			)
		).insert(ignore_permissions=True)
		parent = frappe.get_doc(
			dict(
				doctype="User Timesheet",
				name=marker,
				owner=user.name,
				creation=frappe.utils.now_datetime(),
				timesheet_from=user.name,
				timesheet_from_name="Иван Петров",
				ts_valid_from="2026-11-02",
				ts_valid_for="2026-11-08",
				ut_status="Pending Approval",
			)
		)
		parent.db_insert()
		position = frappe.get_doc(
			dict(
				doctype="User Timesheet Position",
				name=marker + "-position",
				creation=frappe.utils.now_datetime(),
				owner=user.name,
				user=user.name,
				user_timesheet=parent.name,
				all_hours=8,
				table=[
					dict(date="2026-11-02", hours=2, description="тестирование"),
					dict(date="2026-11-03", hours=3.5, description="доработка"),
					dict(date="2026-11-04", hours=2.5, description="документация"),
					dict(date="2026-11-05", hours=0, description="неиспользованный день"),
				],
			)
		)
		position.db_insert()
		for idx, row in enumerate(position.table, 1):
			row.parent, row.parenttype, row.parentfield, row.idx = (
				position.name,
				position.doctype,
				"table",
				idx,
			)
			row.db_insert()
		loaded = frappe.get_doc(position.doctype, position.name)
		task = frappe._dict(reference_doctype=position.doctype, reference_name=position.name)
		expected = [
			dict(hours=2, description="тестирование"),
			dict(hours=3.5, description="доработка"),
			dict(hours=2.5, description="документация"),
		]
		self.assertEqual(digest_item(task)["hours_details"], expected)
		self.assertEqual(email_context(task, loaded)["hours_details"], expected)
		self.assertEqual(email_context(task, loaded)["hours"], 8)
