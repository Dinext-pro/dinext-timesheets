"""Synthetic, development-server-only acceptance fixtures for deadline UI."""
from datetime import timedelta
from hashlib import sha256
import json
from pathlib import Path
import tempfile

import frappe
from frappe.tests.ui_test_helpers import whitelist_for_tests
from frappe.utils import getdate, nowdate
from frappe.utils.password import update_password

MARKER_KEY = "deadline-ui-fixtures"


def _registry_path(user):
	key = sha256((frappe.local.site + ":" + user).encode()).hexdigest()
	return Path(tempfile.gettempdir()) / "dinext-deadline-ui" / (key + ".json")


def _fixture_info(user):
	path = _registry_path(user)
	return json.loads(path.read_text()) if path.exists() else frappe.cache().hget(MARKER_KEY, user)


def _require_test_request(admin=False):
	if not (frappe.flags.in_test or getattr(frappe.local, "dev_server", False)):
		frappe.throw("Deadline acceptance helpers require a development request", frappe.PermissionError)
	if admin and frappe.session.user != "Administrator":
		frappe.throw("Only Administrator can manage deadline acceptance fixtures", frappe.PermissionError)


@whitelist_for_tests
def seed_deadline_ui():
	_require_test_request(admin=True)
	from dinext_timesheets.tests.test_deadline_integration import TestDeadlineIntegration

	fixture = TestDeadlineIntegration()
	fixture.setUp()
	user = frappe.get_doc("User", fixture.user)
	# Respect site-specific Desk permissions without changing global rules.
	desk_roles = frappe.get_all("Custom DocPerm", filters={
		"parent": ["in", ["Number Card", "Kanban Board", "Task", "Issue"]], "read": 1,
	}, pluck="role")
	for role in dict.fromkeys(["System Manager", "Projects User", "Support Team", *desk_roles]):
		if frappe.db.exists("Role", role):
			user.append("roles", {"role": role})
	user.onboarding_status = json.dumps({
		name: {"is_complete": True} for name in frappe.get_all("Form Tour", pluck="name")
	})
	user.language = "en"
	user.save(ignore_permissions=True)
	password = frappe.generate_hash(length=24)
	update_password(fixture.user, password)
	fixture.calendar.set("holidays", [])
	fixture.calendar.save(ignore_permissions=True)
	doc = fixture.timesheet()
	today = getdate(nowdate())
	doc.ts_valid_from = today - timedelta(days=10)
	doc.ts_valid_for = today - timedelta(days=6)
	doc.save(ignore_permissions=True)
	empty = fixture.timesheet()
	frappe.db.set_value("User Timesheet", empty.name, "ts_date_of_dispatch", None)
	pending = fixture.timesheet()
	frappe.db.set_value("User Timesheet", pending.name, {
		"ut_status": fixture.status("Pending Approval"), "ts_date_of_dispatch": today - timedelta(days=2),
	})
	result = {"user": fixture.user, "password": password, "timesheet": doc.name,
		"deadline": str(doc.ts_date_of_dispatch), "next_period_end": str(doc.ts_valid_for + timedelta(days=1)),
		"next_deadline": str(doc.ts_valid_for + timedelta(days=2)), "empty": empty.name, "pending": pending.name,
		"marker": fixture.marker}
	# Keep only identities required for cleanup, never the generated password.
	registry = {
		"timesheets": [doc.name, empty.name, pending.name], "worker": fixture.worker.name,
		"template": fixture.template.name, "calendar": fixture.calendar.name,
		"hours": fixture.hours.name, "group": fixture.group.name,
	}
	path = _registry_path(fixture.user)
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(json.dumps(registry))
	return result


@whitelist_for_tests
def set_deadline_language(language: str):
	_require_test_request()
	user = frappe.session.user
	if language not in ("en", "ru") or not _fixture_info(user):
		frappe.throw("Only synthetic deadline users can change acceptance language")
	frappe.db.set_value("User", user, "language", language)
	frappe.db.after_commit.add(lambda: frappe.clear_cache(user=user))


@whitelist_for_tests
def cleanup_deadline_ui(user: str):
	_require_test_request(admin=True)
	data = _fixture_info(user)
	if not data:
		return
	for name in data["timesheets"]:
		if frappe.db.exists("User Timesheet", name):
			frappe.delete_doc("User Timesheet", name, ignore_permissions=True, force=True)
	for dt, key in [("Worker", "worker"), ("Timesheet Template", "template"),
		("Working Hours On Date", "hours"), ("Holiday List", "calendar"), ("User Group", "group")]:
		if frappe.db.exists(dt, data[key]):
			frappe.delete_doc(dt, data[key], ignore_permissions=True, force=True)
	if frappe.db.exists("User", user):
		frappe.delete_doc("User", user, ignore_permissions=True, force=True)
	frappe.cache().hdel(MARKER_KEY, user)
	_registry_path(user).unlink(missing_ok=True)
