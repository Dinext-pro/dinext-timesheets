# Copyright (c) 2026, Dinext and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from dinext_timesheets.timesheet_settings import validate_timesheet_settings


class TimesheetSettings(Document):
	def validate(self):
		validate_timesheet_settings(self)
