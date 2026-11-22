"""Restore named Timesheet Settings rows after a browser fixture replaces them."""

from pathlib import Path
from tempfile import NamedTemporaryFile

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


def _snapshot_path(key) -> Path:
	return Path(frappe.get_site_path("private", key + ".json"))


def read_snapshot(key):
	path = _snapshot_path(key)
	return frappe.parse_json(path.read_text(encoding="utf-8")) if path.exists() else frappe.cache.get_value(key)


def save_snapshot(key, data):
	path = _snapshot_path(key)
	# Settings must survive an unrelated cache clear while the browser is open.
	with NamedTemporaryFile(dir=path.parent, mode="w", encoding="utf-8", delete=False) as stream:
		try:
			stream.write(frappe.as_json(data))
			stream.close()
			Path(stream.name).replace(path)
		finally:
			Path(stream.name).unlink(missing_ok=True)


def discard_snapshot(key):
	_snapshot_path(key).unlink(missing_ok=True)
	frappe.cache.delete_value(key)



def discard_snapshot_after_commit(key):
	path = _snapshot_path(key)
	inode = path.stat().st_ino if path.exists() else None

	def discard_matching_snapshot():
		current = path.stat().st_ino if path.exists() else None
		if current == inode:
			discard_snapshot(key)

	# Seed may replace the old backup before committing the preceding cleanup.
	frappe.db.after_commit.add(discard_matching_snapshot)
