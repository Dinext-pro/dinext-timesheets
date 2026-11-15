"""Direct approval uses the saved timesheet, worker calendar and document hooks."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate, nowdate

from dinext_timesheets import workflow_approval
from dinext_timesheets.dinext_timesheets.user_timesheet.events import journal, user_timesheet_position

APPROVE = "Approve"
RETURN = "Return to Editing"
DAY = "2026-11-07"
NEXT_DAY = "2026-11-08"


class TestEmptyTimesheetApproval(FrappeTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self.marker = "empty-ut-" + frappe.generate_hash(length=10)
		self.worker = self.make_user("worker", "Dinext_Worker")
		self.lead = self.make_user("lead", "Dinext_Worker", "Dinext_Team_Lead")
		self.other = self.make_user("other", "Dinext_Worker", "Dinext_Team_Lead")
		self.calendar = self.insert("Holiday List", {
			"holiday_list_name": self.marker, "from_date": "2026-11-01", "to_date": "2026-11-30",
			"holidays": [{"holiday_date": DAY, "description": "Holiday"}],
		})
		self.hours = self.insert("Working Hours On Date", {
			"hod_subject": self.marker, "hod_from_date": "2026-11-01", "hod_to_date": "2026-11-30",
			"hod_working_hours_table": [{"wht_date": NEXT_DAY, "wht_hours": 6}],
		})
		self.template = self.insert("Timesheet Template", {
			"ttsubject": self.marker, "enabled": 1, "ttreporting_period": "Недельный",
			"hours_on_date": 8, "minimum_hours": 2, "maximum_hours": 2,
			"tt_working_hours_on_date": self.hours.name, "working_days": 0,
			"doctype_for_timesheet": [{"dtdoctype": "Task"}],
		})
		group = self.insert("User Group", {
			"user_group_members": [{"user": self.worker}, {"user": self.lead}],
		}, set_name=self.marker)
		# Only the lead at the start of the period can manage the empty sheet.
		for lead, start in [(self.lead, "2026-11-01"), (self.other, NEXT_DAY)]:
			frappe.get_doc({
				"doctype": "Teamleads Table", "parent": group.name, "parenttype": "User Group",
				"parentfield": "custom_table", "teamlead": lead, "date": start,
			}).db_insert()
		self.insert("Worker", {
			"wuser": self.worker, "wuser_group": group.name, "wtimesheet_template": self.template.name,
			"wholiday_list": self.calendar.name, "wvalid_from": "2026-11-01",
		})
		self.sheet = self.make_timesheet()

	def tearDown(self):
		frappe.set_user("Administrator")
		super().tearDown()

	def insert(self, doctype, fields, **kwargs):
		return frappe.get_doc({"doctype": doctype, **fields}).insert(ignore_permissions=True, **kwargs)

	def make_user(self, key, *roles):
		email = f"{self.marker}-{key}@example.com"
		return self.insert("User", {
			"email": email, "first_name": f"{self.marker}-{key}", "send_welcome_email": 0,
			"roles": [{"role": role} for role in roles],
		}).name

	def make_timesheet(self):
		return self.insert("User Timesheet", {
			"timesheet_from": self.worker, "timesheet_from_name": self.marker,
			"ts_valid_from": DAY, "ts_valid_for": NEXT_DAY, "ts_from_template": self.template.name,
			"ut_status": "Draft",
		}, set_name=self.marker + "-" + frappe.generate_hash(length=8))

	def add_holiday(self):
		self.calendar.append("holidays", {"holiday_date": NEXT_DAY, "description": "Weekend"})
		self.calendar.save(ignore_permissions=True)

	def leave(self, hours, status="Approved", start=NEXT_DAY):
		frappe.get_doc({
			"doctype": "Application For Leave", "name": f"{self.marker}-{status}",
			"lauser": self.worker, "status": status,
			"alfrom_date": start, "alto_date": NEXT_DAY, "alfrom_hours": hours,
		}).db_insert()

	def actions(self, actor):
		frappe.set_user(actor)
		return [
			row["action"] for row in workflow_approval.get_timesheet_position_actions(self.sheet.name)["actions"]
			if row.get("scope") == "timesheet"
		]

	def apply(self, actor, action=APPROVE, request_id=None):
		frappe.set_user(actor)
		return workflow_approval.apply_timesheet_position_action(
			self.sheet.name, action, scope="timesheet", request_id=request_id,
		)

	def assert_status(self, status):
		self.sheet.reload()
		self.assertEqual(self.sheet.ut_status, status)

	def test_owner_and_period_start_lead_can_approve_and_reopen(self):
		self.add_holiday()
		self.assertEqual(self.actions(self.worker), [APPROVE])
		self.assertEqual(self.actions(self.lead), [APPROVE])
		with patch.object(journal, "call_whitelisted_function", wraps=journal.call_whitelisted_function) as post:
			request_id = self.marker + "-approve"
			result = self.apply(self.worker, request_id=request_id)
			self.assertEqual(result, self.apply(self.worker, request_id=request_id))
			self.assert_status("Approved")
			self.assertEqual(getdate(self.sheet.ut_approval_date), getdate(nowdate()))
			self.assertEqual(self.sheet.utilization, 0)
			self.assertEqual(self.sheet.total_hours_worked, 0)
			self.assertEqual(self.actions(self.lead), [RETURN])
			self.apply(self.lead, RETURN, request_id=self.marker + "-reopen")
			self.assert_status("Rework")
			self.assertFalse(self.sheet.ut_approval_date)
			self.assertEqual([call.args[0] for call in post.call_args_list], [
				"create_journal_entries_for_approved_timesheet",
				"cancelled_journal_entries_for_rejected_timesheet.process_rejected_timesheet",
			])
		self.apply(self.lead)
		self.apply(self.worker, RETURN)
		self.assert_status("Rework")

	def test_approved_absence_covers_reduced_hours_on_a_workday(self):
		self.leave(6)
		self.assertEqual(self.actions(self.worker), [APPROVE])
		self.apply(self.worker)
		self.assert_status("Approved")
		self.assertEqual(self.sheet.total_hours_schedule, 6)
		self.assertEqual(self.sheet.total_hours_leave, 6)
		self.assertEqual(self.sheet.total_hours_to_work, 0)

	def test_leave_start_before_period_does_not_reduce_a_full_day_inside_it(self):
		self.sheet.ts_valid_from = NEXT_DAY
		self.sheet.save(ignore_permissions=True)
		self.leave(4, start=DAY)
		self.apply(self.worker)
		self.assert_status("Approved")
		self.assertEqual(self.sheet.total_hours_leave, 6)
		self.assertEqual(self.sheet.total_hours_to_work, 0)

	def test_uncovered_or_unapproved_hours_are_ineligible(self):
		for leave in [None, (6, "Pending Approval"), (5, "Approved")]:
			with self.subTest(leave=leave):
				if leave:
					self.leave(*leave)
				self.assertEqual(self.actions(self.worker), [])
				with self.assertRaises(frappe.ValidationError):
					self.apply(self.worker)
				self.assert_status("Draft")

	def test_return_after_calendar_change(self):
		self.add_holiday()
		self.apply(self.worker)
		frappe.set_user("Administrator")
		self.calendar.remove(self.calendar.holidays[-1])
		self.calendar.save(ignore_permissions=True)
		self.assertEqual(self.actions(self.lead), [RETURN])
		self.apply(self.lead, RETURN)
		self.assert_status("Rework")
		self.assertEqual(self.actions(self.worker), [])
		with self.assertRaises(frappe.ValidationError):
			self.apply(self.worker)

	def test_calendar_no_longer_covers_the_period(self):
		self.add_holiday()
		frappe.db.set_value("Holiday List", self.calendar.name, "to_date", DAY)
		self.assertEqual(self.actions(self.worker), [])
		with self.assertRaises(frappe.ValidationError):
			self.apply(self.worker)
		self.assert_status("Draft")

	def test_period_overlap_blocks_approval(self):
		self.add_holiday()
		self.make_timesheet()
		with self.assertRaises(frappe.ValidationError):
			self.apply(self.worker)
		self.assert_status("Draft")

	def test_unauthorized_user_cannot_apply_or_bypass_workflow(self):
		self.add_holiday()
		with self.assertRaises(frappe.PermissionError):
			self.apply(self.other)
		self.assert_status("Draft")
		frappe.set_user(self.worker)
		self.sheet.ut_status = "Approved"
		with self.assertRaises(frappe.PermissionError):
			self.sheet.save(ignore_permissions=False)
		self.assert_status("Draft")

	def test_existing_position_and_late_insert_cannot_use_empty_approval(self):
		self.add_holiday()
		position = frappe.get_doc({
			"doctype": "User Timesheet Position", "user_timesheet": self.sheet.name, "user": self.worker,
		})
		position.db_insert()
		self.assertEqual(self.actions(self.worker), [])
		with self.assertRaises(frappe.ValidationError):
			self.apply(self.worker)
		frappe.db.delete("User Timesheet Position", {"name": position.name})
		self.apply(self.worker)
		frappe.set_user("Administrator")
		late_position = frappe.new_doc("User Timesheet Position")
		late_position.user_timesheet = self.sheet.name
		late_position.flags.ignore_permissions = True
		with self.assertRaises(frappe.ValidationError):
			user_timesheet_position.before_insert(late_position)

	def test_handler_failure_rolls_back_status_and_the_request_can_be_retried(self):
		self.add_holiday()
		request_id = self.marker + "-retry"
		with patch.object(journal, "call_whitelisted_function", side_effect=RuntimeError("posting failed")):
			with self.assertRaisesRegex(RuntimeError, "posting failed"):
				self.apply(self.worker, request_id=request_id)
		self.assert_status("Draft")
		self.assertFalse(self.sheet.ut_approval_date)
		self.apply(self.worker, request_id=request_id)
		self.assert_status("Approved")
