import frappe

from dinext_timesheets.tests.test_deadline_integration import TestDeadlineIntegration as Base


class TestSubmissionEvents(Base):
	def test_legacy_rework_submission_keeps_unknown_first_and_records_a_resubmission(self):
		from dinext_timesheets.submission_discipline import submission_result

		parent = self.timesheet()
		frappe.db.set_value(
			"User Timesheet",
			parent.name,
			{"creation": "2020-01-01 10:00:00", "ut_status": self.status("Rework")},
		)
		parent.reload()
		parent.ut_status = self.status("Pending Approval")
		parent.save(ignore_permissions=True)
		events = frappe.get_all(
			"Timesheet Submission Event", filters={"timesheet": parent.name}, fields=["*"]
		)
		self.assertEqual(len(events), 1)
		result = submission_result(
			events, today="2026-11-30", current_deadline="2026-11-09", history_tracked=False
		)
		self.assertEqual(result["status"], "Unknown")
		self.assertEqual(result["resubmissions"], 1)
		self.assertIsNone(result["actual"])

	def test_timesheet_report_period_excludes_closed_old_parents_before_loading_documents(self):
		from dinext_timesheets.submission_discipline import visible_data

		current = self.timesheet()
		old = frappe.copy_doc(current)
		old.name = self.marker + "-old-parent"
		old.update(
			dict(
				ut_status=self.status("Approved"),
				ts_date_of_dispatch="2020-01-01",
				creation="2020-01-01 10:00:00",
			)
		)
		old.db_insert()
		rows = visible_data({"author": self.user, "from_date": "2026-11-01", "to_date": "2026-11-30"})
		self.assertIn(current.name, {row["timesheet"] for row in rows})
		self.assertNotIn(old.name, {row["timesheet"] for row in rows})

	def test_leave_email_replaces_user_id_in_native_document_name_with_full_name(self):
		from dinext_common.workflow_approval.email_presentation import render_standard

		from dinext_timesheets.workflow_email import digest_item, email_context

		user = frappe.get_doc("User", self.user)
		user.first_name = "Иван"
		user.last_name = "Петров"
		user.language = "ru"
		user.save(ignore_permissions=True)
		source = frappe.get_doc(
			dict(
				doctype="Application For Leave",
				name="2026-11-10 - 2026-11-11 -" + self.user,
				lauser=self.user,
				owner=self.user,
			)
		)
		source.db_insert()
		task = frappe._dict(reference_doctype=source.doctype, reference_name=source.name)
		context = email_context(task, source)
		self.assertIn("Иван Петров", context["document_title"])
		self.assertNotIn(self.user, context["document_title"])
		row = dict(
			doctype=source.doctype,
			name=source.name,
			link="/app/application-for-leave/example",
			actions=[],
			**digest_item(task),
		)
		_subject, body = render_standard("Dinext Workflow Digest", {"rows": [row]}, self.user)
		self.assertIn("Иван Петров", body)
		self.assertNotIn(self.user, body)

	def test_first_event_is_frozen_resubmission_is_separate_and_retry_idempotent(self):
		from dinext_timesheets.submission_discipline import record_submission, submission_result

		parent = self.timesheet()
		record_submission(parent, event_key="first", submitted_at="2026-11-09 16:00:00")
		record_submission(parent, event_key="first", submitted_at="2026-11-09 16:00:00")
		frappe.db.set_value("User Timesheet", parent.name, "ts_date_of_dispatch", "2026-11-10")
		record_submission(parent, event_key="again", submitted_at="2026-11-12 16:00:00")
		rows = frappe.get_all(
			"Timesheet Submission Event",
			filters={"timesheet": parent.name},
			fields=["*"],
			order_by="submitted_at asc",
		)
		self.assertEqual(len(rows), 2)
		self.assertEqual([row.first_submission for row in rows], [1, 0])
		result = submission_result(rows, today="2026-11-13", current_deadline="2026-11-10")
		self.assertEqual(result["status"], "On Time")
		self.assertEqual(str(result["deadline"]), "2026-11-09")

	def test_submission_report_does_not_accept_foreign_author_filter(self):
		from dinext_timesheets.submission_discipline import visible_data

		parent = self.timesheet()
		frappe.set_user(self.user)
		self.assertTrue(any(row["timesheet"] == parent.name for row in visible_data({"author": self.user})))
		self.assertEqual(visible_data({"author": "Administrator"}), [])

	def test_saved_parent_transition_records_complete_submission_via_hook(self):
		parent = self.timesheet()
		parent.ut_status = self.status("Pending Approval")
		parent.save(ignore_permissions=True)
		events = frappe.get_all(
			"Timesheet Submission Event", filters={"timesheet": parent.name}, fields=["first_submission"]
		)
		self.assertEqual(len(events), 1)
		self.assertEqual(events[0].first_submission, 1)

	def test_email_parent_link_requires_recipient_access_to_parent_timesheet(self):
		from dinext_timesheets.workflow_email import can_receive

		parent = self.timesheet()
		source = frappe._dict(doctype="User Timesheet Position", user_timesheet=parent.name)
		other = self.marker + "-email-other@example.com"
		frappe.get_doc(
			dict(
				doctype="User",
				email=other,
				first_name="Other Reader",
				send_welcome_email=0,
				roles=[{"role": "Dinext_Worker"}],
			)
		).insert(ignore_permissions=True)
		self.assertTrue(can_receive(None, source, self.user))
		self.assertFalse(can_receive(None, source, other))
