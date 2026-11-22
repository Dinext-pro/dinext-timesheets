# Copyright (c) 2026, Dinext and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from dinext_timesheets.application_for_leave import (
	validate_application_for_leave,
	validate_leave_overlap,
)


class ApplicationForLeave(Document):
	def before_validate(self) -> None:
		validate_leave_overlap(self)

	def validate(self) -> None:
		validate_application_for_leave(self)
