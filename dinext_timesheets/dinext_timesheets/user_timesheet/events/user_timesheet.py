"""User Timesheet doc_events (ISS-2026-00926 phase 2)."""

from __future__ import annotations

from dinext_timesheets.deadlines import prepare_dispatch_date

from .hours import calculate_ut_hours
from .journal import maybe_create_or_cancel_journal_entries
from .ownership import set_ut_user_group


def before_save(doc, method=None):
	prepare_dispatch_date(doc)
	set_ut_user_group(doc)
	calculate_ut_hours(doc)


def on_update(doc, method=None):
	# Demodev SS "After Save" → Document.on_update
	maybe_create_or_cancel_journal_entries(doc, method)
