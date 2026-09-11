"""Disable UTP_UT_Status_V3 on current site (ISS-2026-03288 layer 3 cutover)."""

import frappe


def run():
	name = "UTP_UT_Status_V3"
	if not frappe.db.exists("Server Script", name):
		return f"missing:{name}"
	frappe.db.set_value("Server Script", name, "disabled", 1)
	frappe.clear_cache()
	frappe.db.commit()
	return f"disabled:{name}={frappe.db.get_value('Server Script', name, 'disabled')}"
