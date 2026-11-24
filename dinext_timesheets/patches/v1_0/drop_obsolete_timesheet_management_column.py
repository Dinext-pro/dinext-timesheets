"""Drop the backing column after remove_timesheet_management_action removed its metadata."""

import frappe

from dinext_timesheets.patches.v1_0.remove_timesheet_management_action import FIELDNAME

DOCTYPE = "Workflow Transition"


def execute():
	if not frappe.db.has_column(DOCTYPE, FIELDNAME):
		return

	if frappe.get_meta(DOCTYPE, cached=False).has_field(FIELDNAME):
		frappe.throw("Remove the obsolete Timesheets management Custom Field before dropping its column.")

	# Frappe keeps removed custom fields in the table. Its DDL helper handles the schema boundary.
	quote = '"' if frappe.conf.db_type == "postgres" else "`"
	table = frappe.qb.DocType(DOCTYPE).get_sql(quote_char=quote)
	frappe.db.sql_ddl(f"ALTER TABLE {table} DROP COLUMN {FIELDNAME}")
