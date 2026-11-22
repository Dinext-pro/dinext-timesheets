"""User Timesheet JE trigger on status change (ISS-2026-00926 phase 2 D).

Port of demodev ``Create Journal Entries UT After Save``.
JE create/cancel bodies stay API Server Scripts for now:
- ``create_journal_entries_for_approved_timesheet``
- ``cancelled_journal_entries_for_rejected_timesheet.process_rejected_timesheet``

Wired on User Timesheet.on_update; JE API bodies remain Server Scripts until full port.
"""

from __future__ import annotations

from frappe.utils.safe_exec import call_whitelisted_function

from dinext_timesheets.timesheet_status import APPROVED_TIMESHEET_STATUSES


def maybe_create_or_cancel_journal_entries(doc, method=None):
	old_doc = doc.get_doc_before_save()
	if not old_doc:
		return

	was_approved = old_doc.ut_status in APPROVED_TIMESHEET_STATUSES
	is_approved = doc.ut_status in APPROVED_TIMESHEET_STATUSES
	if not was_approved and is_approved:
		call_whitelisted_function(
			"create_journal_entries_for_approved_timesheet",
			doc=doc,
		)
	elif was_approved and not is_approved:
		call_whitelisted_function(
			"cancelled_journal_entries_for_rejected_timesheet.process_rejected_timesheet",
			user_timesheet_name=doc.name,
		)
