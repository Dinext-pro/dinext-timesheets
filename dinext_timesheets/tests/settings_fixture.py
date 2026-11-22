"""Restore named Timesheet Settings rows after a browser fixture replaces them."""

import frappe


def restore_timesheet_settings_rows(**snapshots):
	settings = frappe.get_single("Timesheet Settings")
	for fieldname, snapshot in snapshots.items():
		if snapshot is None:
			continue
		persisted_names = {row.name for row in settings.get(fieldname)}
		settings.set(fieldname, snapshot)
		for row in settings.get(fieldname):
			if row.name not in persisted_names:
				# The fixture deleted this named row, so Frappe must insert it again.
				row.set("__islocal", 1)
		settings.update_child_table(fieldname)


