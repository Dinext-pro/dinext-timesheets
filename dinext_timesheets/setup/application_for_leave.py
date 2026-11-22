"""Disable the database scripts superseded by the Application For Leave controller."""

import frappe


SUPERSEDED_SERVER_SCRIPTS = ("AFL_Calculate_Hours", "AFL_Projects")


def disable_superseded_server_scripts() -> None:
	names = frappe.get_all(
		"Server Script",
		filters={"name": ("in", SUPERSEDED_SERVER_SCRIPTS), "disabled": 0},
		pluck="name",
	)
	for name in names:
		frappe.db.set_value("Server Script", name, "disabled", 1, update_modified=False)
	if names:
		frappe.cache.delete_value("server_script_map")
