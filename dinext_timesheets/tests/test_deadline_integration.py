"""Exercise persisted deadlines and permission-aware summaries on a Frappe site."""
from datetime import date
from unittest.mock import patch
import frappe
from frappe.tests.utils import FrappeTestCase


class TestDeadlineIntegration(FrappeTestCase):
    def setUp(self):
        super().setUp()
        frappe.set_user("Administrator")
        self.marker = "deadline-" + frappe.generate_hash(length=8)
        self.user = self.marker + "@example.com"
        frappe.get_doc({"doctype": "User", "email": self.user, "first_name": self.marker,
                        "enabled": 1, "send_welcome_email": 0,
                        "roles": [{"role": "Dinext_Worker"}]}).insert(ignore_permissions=True)
        self.group = frappe.get_doc({"doctype": "User Group", "name": self.marker, "user_group_members": [{"user": self.user}]}).insert(ignore_permissions=True, set_name=self.marker)
        self.calendar = frappe.get_doc({"doctype": "Holiday List", "holiday_list_name": self.marker,
            "from_date": "2026-01-01", "to_date": "2027-12-31", "holidays": [
                {"holiday_date": day, "description": "Weekend"} for day in ("2026-11-07", "2026-11-08")]}).insert(ignore_permissions=True)
        self.hours = frappe.get_doc({"doctype": "Working Hours On Date", "hod_subject": self.marker,
            "hod_from_date": "2026-01-01", "hod_to_date": "2027-12-31"}).insert(ignore_permissions=True)
        self.template = frappe.get_doc({"doctype": "Timesheet Template", "ttsubject": self.marker,
            "enabled": 1, "doctype_for_timesheet": [{"dtdoctype": "Task"}],
            "tt_working_hours_on_date": self.hours.name, "ttreporting_period": "Недельный",
            "hours_on_date": 8, "minimum_hours": 0, "maximum_hours": 8, "working_days": 1}).insert(ignore_permissions=True)
        self.worker = frappe.get_doc({"doctype": "Worker", "wuser": self.user,
            "wuser_group": self.group.name, "wtimesheet_template": self.template.name,
            "wholiday_list": self.calendar.name, "wvalid_from": "2026-01-01"}).insert(ignore_permissions=True)

    def tearDown(self):
        frappe.set_user("Administrator")
        super().tearDown()

    def status(self, key):
        options = frappe.get_meta("User Timesheet").get_field("ut_status").options.splitlines()
        if key in options:
            return key
        return {"Draft": "Черновик", "Rework": "На доработке", "Rejected": "Отклонено",
                "Pending Approval": "На согласовании", "Approved": "Согласован"}[key]

    def timesheet(self):
        return frappe.get_doc({"doctype": "User Timesheet", "timesheet_from": self.user,
            "ts_from_template": self.template.name, "ts_valid_from": "2026-11-02",
            "ts_valid_for": "2026-11-06", "ut_status": self.status("Draft")}).insert(ignore_permissions=True, set_name=self.marker + "-" + frappe.generate_hash(length=8))

    def test_insert_and_repeated_editable_saves_use_period_end(self):
        doc = self.timesheet()
        self.assertEqual(str(doc.ts_date_of_dispatch), "2026-11-09")
        self.template.working_days = 2
        self.template.save(ignore_permissions=True)
        doc.save(ignore_permissions=True)
        self.assertEqual(str(doc.ts_date_of_dispatch), "2026-11-10")
        doc.save(ignore_permissions=True)
        self.assertEqual(str(doc.ts_date_of_dispatch), "2026-11-10")
        doc.ts_valid_for = "2026-11-09"
        doc.save(ignore_permissions=True)
        self.assertEqual(str(doc.ts_date_of_dispatch), "2026-11-11")

    def test_noneditable_preserves_date_and_rework_recalculates(self):
        doc = self.timesheet()
        self.template.working_days = 2
        self.template.save(ignore_permissions=True)
        for status in ("Pending Approval", "Rejected", "Approved"):
            frappe.db.set_value("User Timesheet", doc.name, "ut_status", self.status(status))
            doc.reload()
            doc.ts_date_of_dispatch = "2026-11-30"
            doc.save(ignore_permissions=True)
            self.assertEqual(str(doc.ts_date_of_dispatch), "2026-11-09")
        frappe.db.set_value("User Timesheet", doc.name, "ut_status", self.status("Rework"))
        doc.reload().save(ignore_permissions=True)
        self.assertEqual(str(doc.ts_date_of_dispatch), "2026-11-10")

    def test_old_empty_date_is_filled_only_on_editable_save(self):
        doc = self.timesheet()
        frappe.db.set_value("User Timesheet", doc.name, {"ts_date_of_dispatch": None, "ut_status": self.status("Rejected")})
        doc.reload().save(ignore_permissions=True)
        self.assertFalse(doc.ts_date_of_dispatch)
        frappe.db.set_value("User Timesheet", doc.name, "ut_status", self.status("Rework"))
        doc.reload().save(ignore_permissions=True)
        self.assertEqual(str(doc.ts_date_of_dispatch), "2026-11-09")

    def test_template_precedence_calendar_change_and_zero(self):
        doc = self.timesheet()
        other = frappe.copy_doc(self.template)
        other.ttsubject = self.marker + "-other"
        other.working_days = 2
        other.insert(ignore_permissions=True)
        self.worker.wtimesheet_template = other.name
        self.worker.save(ignore_permissions=True)
        doc.save(ignore_permissions=True)
        self.assertEqual(str(doc.ts_date_of_dispatch), "2026-11-09")
        doc.ts_from_template = None
        doc.save(ignore_permissions=True)
        self.assertEqual(str(doc.ts_date_of_dispatch), "2026-11-10")
        other.working_days = 0
        other.save(ignore_permissions=True)
        doc.save(ignore_permissions=True)
        self.assertEqual(str(doc.ts_date_of_dispatch), "2026-11-06")
        doc.ts_from_template = self.template.name
        self.calendar.remove(self.calendar.holidays[0])
        self.calendar.save(ignore_permissions=True)
        doc.save(ignore_permissions=True)
        self.assertEqual(str(doc.ts_date_of_dispatch), "2026-11-07")

    def test_negative_template_days_are_rejected(self):
        self.template.working_days = -1
        with self.assertRaises(frappe.ValidationError):
            self.template.save(ignore_permissions=True)

    def test_scheduler_continues_after_invalid_worker_calendar(self):
        from dinext_timesheets.dinext_timesheets.user_timesheet import scheduler
        bad_user = self.marker + "-bad@example.com"
        frappe.get_doc({"doctype": "User", "email": bad_user, "first_name": self.marker + " bad",
                        "send_welcome_email": 0}).insert(ignore_permissions=True)
        bad_calendar = frappe.copy_doc(self.calendar)
        bad_calendar.holiday_list_name = self.marker + "-bad"
        bad_calendar.to_date = "2026-11-08"
        bad_calendar.insert(ignore_permissions=True)
        bad_worker = frappe.copy_doc(self.worker)
        bad_worker.wuser = bad_user
        bad_worker.wholiday_list = bad_calendar.name
        bad_worker.insert(ignore_permissions=True)
        self.template.automatically = 1
        self.template.save(ignore_permissions=True)
        original_list = frappe.get_list
        original_getdate = scheduler.getdate
        def template_scope(doctype, *args, **kwargs):
            if doctype == "Timesheet Template":
                return [frappe._dict(name=self.template.name)]
            return original_list(doctype, *args, **kwargs)
        with patch.object(scheduler.frappe, "get_list", side_effect=template_scope), patch.object(
            scheduler, "getdate", side_effect=lambda value=None: original_getdate(value or "2026-11-02")
        ):
            result = scheduler.create_weekly_timesheets()
        self.assertEqual(len(result["created"]), 1)
        self.assertEqual(frappe.session.user, "Administrator")
        self.assertEqual(frappe.db.get_value("User Timesheet", result["created"][0]["name"], "owner"), "Administrator")
        self.assertEqual(result["created"][0]["user"], self.user)
        self.assertEqual(result["skipped"][0]["reason"], "validation_error")
        self.assertFalse(frappe.db.exists("User Timesheet", {"timesheet_from": bad_user}))

    def test_ui_fixture_rejects_cached_module_outside_dev_requests(self):
        from dinext_timesheets.tests.deadline_ui import seed_deadline_ui
        original_test = frappe.flags.in_test
        original_dev = getattr(frappe.local, "dev_server", 0)
        try:
            frappe.flags.in_test = False
            frappe.local.dev_server = False
            with self.assertRaises(frappe.PermissionError):
                seed_deadline_ui()
        finally:
            frappe.flags.in_test = original_test
            frappe.local.dev_server = original_dev
        frappe.set_user(self.user)
        with self.assertRaises(frappe.PermissionError):
            seed_deadline_ui()

    def test_split_week_creation_is_atomic_and_retryable(self):
        from dinext_timesheets.dinext_timesheets.user_timesheet import scheduler
        self.calendar.to_date = "2026-12-02"
        self.calendar.save(ignore_permissions=True)
        self.template.automatically = 1
        self.template.save(ignore_permissions=True)
        original_list = frappe.get_list
        original_getdate = scheduler.getdate
        def template_scope(doctype, *args, **kwargs):
            if doctype == "Timesheet Template":
                return [frappe._dict(name=self.template.name)]
            return original_list(doctype, *args, **kwargs)
        with patch.object(scheduler.frappe, "get_list", side_effect=template_scope), patch.object(
            scheduler, "getdate", side_effect=lambda value=None: original_getdate(value or "2026-11-30")
        ):
            first = scheduler.create_weekly_timesheets()
            self.assertEqual(first["created"], [])
            self.assertFalse(frappe.db.exists("User Timesheet", {"timesheet_from": self.user}))
            self.calendar.to_date = "2026-12-31"
            self.calendar.save(ignore_permissions=True)
            second = scheduler.create_weekly_timesheets()
        self.assertEqual(len(second["created"]), 2)

    def test_fresh_install_has_metadata_cutover_after_fixture_sync(self):
        self.assertIn("dinext_timesheets.setup.deadlines.configure_deadline_metadata",
                      frappe.get_hooks("after_sync", app_name="dinext_timesheets"))

    def test_metadata_cutover_is_idempotent_and_does_not_backfill(self):
        from dinext_timesheets.setup.deadlines import configure_deadline_metadata
        doc = self.timesheet()
        frappe.db.set_value("User Timesheet", doc.name, "ts_date_of_dispatch", None)
        if not frappe.db.exists("Client Script", "Task_Timesheet_Overdue"):
            frappe.get_doc({"doctype": "Client Script", "name": "Task_Timesheet_Overdue",
                "dt": "Task", "script": "// Synthetic duplicate", "enabled": 1}).insert(ignore_permissions=True)
        frappe.db.set_value("Client Script", "Task_Timesheet_Overdue", "enabled", 1)
        for name in ("Таймшит не отправлен", "Таймшит не отправленМ"):
            if not frappe.db.exists("Notification", name):
                frappe.get_doc({"doctype": "Notification", "name": name, "subject": "Synthetic reminder",
                    "document_type": "User Timesheet", "event": "Days After", "channel": "Email",
                    "date_changed": "ts_valid_for", "days_in_advance": 1, "enabled": 0,
                    "message": "Synthetic test notification"}).insert(ignore_permissions=True)
        configure_deadline_metadata()
        configure_deadline_metadata()
        self.assertFalse(frappe.db.get_value("Client Script", "Task_Timesheet_Overdue", "enabled"))
        self.assertFalse(frappe.db.get_value("User Timesheet", doc.name, "ts_date_of_dispatch"))
        card = frappe.get_doc("Number Card", "Мои просроченные таймшиты")
        self.assertEqual(card.type, "Custom")
        self.assertEqual(card.method, "dinext_timesheets.deadlines.get_my_overdue_summary")
        for name in ("Таймшит не отправлен", "Таймшит не отправленМ"):
            notification = frappe.get_doc("Notification", name)
            self.assertEqual(notification.enabled, 0)
            self.assertEqual(notification.date_changed, "ts_date_of_dispatch")
            self.assertEqual(notification.days_in_advance, 1)

    def test_read_state_ignores_stored_flag_and_checks_permission(self):
        from dinext_timesheets.deadlines import get_deadline_state
        doc = self.timesheet()
        frappe.db.set_value("User Timesheet", doc.name, "is_overdue", 0)
        with patch("dinext_timesheets.deadlines.nowdate", return_value="2026-11-10"):
            state = get_deadline_state(doc.name)
            self.assertTrue(state["overdue"])
            self.assertEqual(state["deadline"], "2026-11-09")
        with patch("dinext_timesheets.deadlines.nowdate", return_value="2026-11-09"):
            self.assertFalse(get_deadline_state(doc.name)["overdue"])
        frappe.set_user("Guest")
        with self.assertRaises(frappe.PermissionError):
            get_deadline_state(doc.name)

    def test_summary_is_complete_and_ignores_caller_owner(self):
        from dinext_timesheets.deadlines import get_my_overdue_summary
        docs = [self.timesheet() for _ in range(23)]
        # Unique naming permits explicit names for otherwise identical synthetic periods.
        for doc in docs:
            frappe.db.set_value("User Timesheet", doc.name, "is_overdue", 0)
        empty = self.timesheet()
        frappe.db.set_value("User Timesheet", empty.name, "ts_date_of_dispatch", None)
        frappe.set_user(self.user)
        with patch("dinext_timesheets.deadlines.nowdate", return_value="2026-11-10"):
            summary = get_my_overdue_summary({"timesheet_from": "Administrator"})
        self.assertEqual(summary["value"], 23)
        self.assertEqual(summary["route_options"]["timesheet_from"], self.user)
        options = frappe.get_meta("User Timesheet").get_field("ut_status").options.splitlines()
        self.assertEqual(summary["route_options"]["ut_status"], ["in", [
            status for status in options
            if status in ("Draft", "Rejected", "Rework", "Черновик", "Отклонено", "На доработке")
        ]])
