"""Request a review when the basis of an approved timesheet changes."""

import frappe
from frappe import _
from frappe.utils.user import get_users_with_role

from dinext_timesheets.dinext_timesheets.user_timesheet.permissions import can_reprocess_journal_entries
from dinext_timesheets.timesheet_status import APPROVED_TIMESHEET_STATUSES

TIMESHEET = "User Timesheet"
LEAVE_REVIEW = "Review this approved timesheet because approved leave changed."
PROJECT_REVIEW = "Review this approved timesheet because a project was closed."
LEAVE_FIELDS = ("lauser", "alfrom_date", "alto_date", "alfrom_hours", "alto_hours", "al_total_hours", "altype_of_leave")


def review_changed_leave(doc, method=None):
	previous = doc.get_doc_before_save()
	approved = [row for row in (previous, doc) if row and row.status == "Approved" and row.docstatus != 2]
	if not approved:
		return
	if len(approved) == 2 and all(previous.get(field) == doc.get(field) for field in LEAVE_FIELDS):
		return
	timesheets = set()
	for row in approved:
		if row.lauser and row.alfrom_date and row.alto_date:
			timesheets.update(frappe.get_all(
				TIMESHEET,
				filters={
					"timesheet_from": row.lauser,
					"ts_valid_from": ("<=", row.alto_date),
					"ts_valid_for": (">=", row.alfrom_date),
				},
				pluck="name",
			))
	_assign_reviews(timesheets, LEAVE_REVIEW)


def review_closed_project(doc, method=None):
	previous = doc.get_doc_before_save()
	if not previous or previous.status != "Open" or previous.is_active != "Yes":
		return
	if doc.status == "Open" and doc.is_active == "Yes":
		return
	timesheets = frappe.get_all(
		"User Timesheet Position",
		filters={"project": doc.name, "user_timesheet": ("is", "set")},
		pluck="user_timesheet",
		distinct=True,
	)
	_assign_reviews(timesheets, PROJECT_REVIEW)


def _assign_reviews(names, reason):
	if not names:
		return
	reviewers = sorted(set(get_users_with_role("Dinext_UT_Full_Access")) - {"Administrator"})
	for name in sorted(names):
		timesheet = frappe.get_doc(TIMESHEET, name, for_update=True)
		if timesheet.ut_status not in APPROVED_TIMESHEET_STATUSES:
			continue
		assignee = next(
			(user for user in reviewers if can_reprocess_journal_entries(user)
				and frappe.has_permission(TIMESHEET, "read", doc=timesheet, user=user)),
			"Administrator",
		)
		language = frappe.db.get_value("User", assignee, "language") or "en"
		description = _(reason, lang=language)
		if frappe.db.get_value("ToDo", {
			"reference_type": TIMESHEET, "reference_name": name,
			"status": "Open", "description": description,
		}, "name", for_update=True):
			continue
		frappe.get_doc({
			"doctype": "ToDo", "reference_type": TIMESHEET, "reference_name": name,
			"status": "Open", "priority": "High", "description": description,
			"allocated_to": assignee, "assigned_by": frappe.session.user,
		}).insert(ignore_permissions=True)
