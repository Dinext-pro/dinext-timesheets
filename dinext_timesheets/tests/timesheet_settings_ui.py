"""Owned inactive Workflow and durable settings backup for native acceptance."""

from pathlib import Path

import frappe
from frappe.tests.ui_test_helpers import whitelist_for_tests

WORKFLOW = "_Cypress TS Settings Workflow"
STATE = "_Cypress TS Settings State"


def _backup_path():
	return Path(frappe.get_site_path("private", "cypress-ts-settings-refinements.json"))


def _require_admin():
	if frappe.session.user != "Administrator":
		frappe.throw("Only the test administrator may manage this fixture", frappe.PermissionError)


@whitelist_for_tests
def cleanup_settings_refinements():
	_require_admin()
	path = _backup_path()
	if path.exists():
		doc = frappe.get_single("Timesheet Settings")
		doc.set("visible_list_statuses", frappe.parse_json(path.read_text()))
		doc.save(ignore_permissions=True)
		path.unlink()
	for doctype, name in [("Workflow", WORKFLOW), ("Workflow State", STATE)]:
		if frappe.db.exists(doctype, name):
			frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
	frappe.db.after_commit.add(frappe.clear_cache)
	return {"cleaned": True}


@whitelist_for_tests
def seed_settings_refinements():
	_require_admin()
	cleanup_settings_refinements()
	doc = frappe.get_single("Timesheet Settings")
	_backup_path().write_text(
		frappe.as_json(
			[
				{"position_status": r.position_status, "open_wf_task": int(r.open_wf_task or 0)}
				for r in doc.visible_list_statuses
			]
		)
	)
	frappe.get_doc({"doctype": "Workflow State", "workflow_state_name": STATE}).insert(
		ignore_permissions=True
	)
	frappe.get_doc(
		{
			"doctype": "Workflow",
			"workflow_name": WORKFLOW,
			"document_type": "User Timesheet Position",
			"workflow_state_field": "workflow_state",
			"is_active": 0,
			"states": [{"state": "Pending Approval", "doc_status": "0", "allow_edit": "All"}],
		}
	).insert(ignore_permissions=True)
	frappe.db.after_commit.add(frappe.clear_cache)
	return {"workflow": WORKFLOW, "inactive_state": STATE}


@whitelist_for_tests
def save_owned_workflow():
	_require_admin()
	doc = frappe.get_doc("Workflow", WORKFLOW)
	if not any(r.state == STATE for r in doc.states):
		doc.append("states", {"state": STATE, "doc_status": "0", "allow_edit": "All"})
	doc.save(ignore_permissions=True)
	return {"workflow": doc.name, "inactive_state": STATE}
