"""Owned acceptance data and recoverable settings for position visibility."""

from pathlib import Path

import frappe
from dinext_timesheets.tests import utp_list_ui as base
from frappe.tests.ui_test_helpers import whitelist_for_tests


def _state_path():
	return Path(frappe.get_site_path("private", "cypress-position-visibility.json"))


def _state():
	path = _state_path()
	return frappe.parse_json(path.read_text()) if path.exists() else {}


def _save_state(value):
	path = _state_path()
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(frappe.as_json(value))


def _rules(doc):
	return [
		{"position_status": r.position_status, "open_wf_task": int(r.open_wf_task or 0)}
		for r in doc.visible_list_statuses
	]


def _require_admin():
	if frappe.session.user != "Administrator":
		frappe.throw(
			"Only the test administrator may configure the fixture",
			frappe.PermissionError,
		)


@whitelist_for_tests
def cleanup_visibility():
	_require_admin()
	backup = _state().get("backup")
	if backup is not None:
		doc = frappe.get_single("Timesheet Settings")
		doc.set("visible_list_statuses", backup)
		doc.save(ignore_permissions=True)

	base.cleanup_utp_list()
	_state_path().unlink(missing_ok=True)
	frappe.db.after_commit.add(frappe.clear_cache)
	return {"cleaned": True}


@whitelist_for_tests
def seed_visibility():
	_require_admin()
	cleanup_visibility()
	initial = _rules(frappe.get_single("Timesheet Settings"))
	_save_state({"backup": initial})
	fixture = base.seed_utp_list()
	rows = fixture["positions"]
	frappe.db.set_value(
		"User Timesheet Position",
		rows[0]["name"],
		"status",
		"Approved",
		update_modified=False,
	)
	frappe.db.set_value(
		"User Timesheet Position",
		rows[1]["name"],
		"status",
		"Editing",
		update_modified=False,
	)
	for index, values in {
		0: {"status": "Completed"},
		2: {"approver": fixture["viewer"]},
		3: {"status": "Completed"},
		4: {"status": "Cancelled"},
		5: {"round_status": "Transitioned"},
	}.items():
		frappe.db.set_value("Workflow Task", rows[index]["task"], values, update_modified=False)
	fixture["initial_visible"] = initial
	_save_state({"backup": initial, "fixture": fixture})
	frappe.db.after_commit.add(frappe.clear_cache)
	return fixture


@whitelist_for_tests
def configure_visibility(gated=0, empty=0, restore_initial=0):
	_require_admin()
	fixture = _state().get("fixture")
	if not fixture:
		frappe.throw("Seed the owned visibility fixture first")
	doc = frappe.get_single("Timesheet Settings")
	rows = (
		[]
		if int(empty)
		else [
			{"position_status": "Pending Approval", "open_wf_task": int(gated)},
			{"position_status": "Approved", "open_wf_task": 0},
		]
	)
	if int(restore_initial):
		rows = fixture["initial_visible"]
	doc.set("visible_list_statuses", rows)
	doc.save(ignore_permissions=True)
	return _rules(doc)


@whitelist_for_tests
def complete_visibility_task():
	fixture = _state().get("fixture")
	if not fixture or frappe.session.user != fixture["approver"]:
		frappe.throw(
			"Only the owned approver may complete this fixture task",
			frappe.PermissionError,
		)
	row = fixture["positions"][7]
	task = frappe.get_doc("Workflow Task", row["task"])
	if task.reference_name != row["name"] or task.approver != frappe.session.user:
		frappe.throw("Fixture task does not match the owned position")
	frappe.db.set_value("Workflow Task", task.name, "status", "Completed", update_modified=False)
	return {"position": row["name"]}


@whitelist_for_tests
def reapply_conversion():
	_require_admin()
	from dinext_timesheets.patches.v1_0.visible_position_list import execute

	execute()
	return _rules(frappe.get_single("Timesheet Settings"))
