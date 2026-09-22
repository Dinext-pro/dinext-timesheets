"""Mirror UTP comments onto parent User Timesheet (ISS-2026-00926 phase 2 E).

Port of demodev Server Script ``UTP_comm_2_UT_transfer`` (After Insert on Comment).
"""

from __future__ import annotations

import frappe
from frappe.utils import cstr


def transfer_utp_comment_to_ut(doc, method=None):
	if doc.reference_doctype != "User Timesheet Position":
		return

	ut_name = frappe.db.get_value(
		"User Timesheet Position", doc.reference_name, "user_timesheet"
	)
	if not ut_name:
		return

	new_doc = frappe.new_doc("Comment")
	new_doc.reference_doctype = "User Timesheet"
	new_doc.reference_name = ut_name
	new_doc.subject = doc.subject
	new_doc.comment_type = doc.comment_type
	new_doc.comment_email = doc.comment_email
	new_doc.comment_by = doc.comment_by
	new_doc.published = doc.published
	new_doc.seen = doc.seen
	new_doc.content = cstr(doc.reference_name) + ": " + cstr(doc.content)
	# demodev SS sets ip_adress; field may be absent on this Frappe build
	if new_doc.meta.has_field("ip_adress") and hasattr(doc, "ip_adress"):
		new_doc.ip_adress = doc.ip_adress
	new_doc.insert(ignore_permissions=True)
