# Copyright (c) 2026, Dinext and contributors
# For license information, please see license.txt

import frappe
from frappe import _

from dinext_timesheets.deadlines import validate_working_days
from frappe.model.document import Document


class TimesheetTemplate(Document):
	def validate(self):
		try:
			validate_working_days(self.working_days)
		except ValueError:
			frappe.throw(_("Working Days must be a non-negative integer"))
