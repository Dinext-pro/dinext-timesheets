"""Calendar/overdue behavior; run without a database using unittest."""
import importlib
import unittest
from datetime import date


class TestDeadlineCalendar(unittest.TestCase):
    def api(self):
        try:
            return importlib.import_module("dinext_timesheets.deadlines")
        except ModuleNotFoundError:
            self.fail("The shared deadline implementation is missing")

    def calculate(self, end, days, holidays=(), start="2026-01-01", until="2027-12-31"):
        return self.api().calculate_dispatch_date(end, days, start, until, holidays)

    def test_skips_weekend_and_public_holiday(self):
        self.assertEqual(self.calculate("2026-11-06", 1, ["2026-11-07", "2026-11-08", "2026-11-09"]), date(2026, 11, 10))

    def test_working_saturday_counts(self):
        self.assertEqual(self.calculate("2026-11-06", 1, ["2026-11-08"]), date(2026, 11, 7))

    def test_reduced_hours_do_not_change_calendar_days(self):
        self.assertEqual(self.calculate("2026-11-06", 2), date(2026, 11, 8))

    def test_crosses_year(self):
        self.assertEqual(self.calculate("2026-12-31", 1, ["2027-01-01", "2027-01-02", "2027-01-03"]), date(2027, 1, 4))

    def test_zero_is_period_end_even_if_holiday(self):
        self.assertEqual(self.calculate("2026-11-08", 0, ["2026-11-08"]), date(2026, 11, 8))

    def test_invalid_working_days_are_rejected(self):
        for value in (-1, 1.5, "bad", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.calculate("2026-11-06", value)

    def test_calendar_must_cover_the_count(self):
        with self.assertRaises(ValueError):
            self.calculate("2026-12-31", 1, until="2026-12-31")
        with self.assertRaises(ValueError):
            self.calculate("2026-11-06", 1, start="2026-11-08")

    def test_author_states_only_and_strict_date_boundary(self):
        api = self.api()
        for status in ("Draft", "Rework", "Rejected", "Черновик", "На доработке", "Отклонено"):
            with self.subTest(status=status):
                self.assertTrue(api.is_timesheet_overdue("2026-11-08", status, "2026-11-09"))
                self.assertFalse(api.is_timesheet_overdue("2026-11-09", status, "2026-11-09"))
                self.assertFalse(api.is_timesheet_overdue(None, status, "2026-11-09"))
        for status in ("Pending Approval", "Approved", "На согласовании", "Согласован", None):
            self.assertFalse(api.is_timesheet_overdue("2026-11-08", status, "2026-11-09"))

    def test_summary_filter_explicitly_excludes_missing_dates(self):
        filters = self.api().overdue_filters("author@example.com", "2026-11-09")
        self.assertIn(["ts_date_of_dispatch", "is", "set"], filters)
        self.assertIn(["ts_date_of_dispatch", "<", "2026-11-09"], filters)
        self.assertIn(["timesheet_from", "=", "author@example.com"], filters)


if __name__ == "__main__":
    unittest.main()
