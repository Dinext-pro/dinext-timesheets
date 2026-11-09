"""Conservative recovery from Version events corroborated by position assignments."""

import json

import frappe

from dinext_timesheets.submission_discipline import ensure_submission_tracking, record_submission

ACCEPTED = {"Pending Approval", "Approved", "На согласовании", "Согласован"}
EDITING = {"Draft", "Черновик"}


def _data(version):
	value = version.get("data") or {}
	return json.loads(value) if isinstance(value, str) else value


def proven_submission(versions, positions, tasks, *, current_deadline):
	versions = sorted(versions, key=lambda row: str(row["creation"]))
	for version in versions:
		changes = _data(version).get("changed", [])
		transition = next((row for row in changes if row[0] == "ut_status"), None)
		if not transition:
			continue
		if transition[1] not in EDITING:
			# A prior approval/rework cycle is already visible: a later draft cannot
			# be labelled the first submission when the first entry is missing.
			return None
		if transition[2] not in ACCEPTED:
			continue
		at = str(version["creation"])
		active = [position for position in positions if str(position.get("creation") or "") <= at]
		if not active:
			return None
		for position in active:
			history = [
				task
				for task in tasks
				if task.get("reference_name") == position["name"] and str(task["creation"]) <= at
			]
			latest = max(history, key=lambda row: str(row["creation"]), default=None)
			if not latest or latest["workflow_state"] not in ACCEPTED:
				return None
		deadline = current_deadline
		for later in reversed(versions):
			if str(later["creation"]) <= at:
				continue
			for change in _data(later).get("changed", []):
				if change[0] == "ts_date_of_dispatch":
					deadline = change[1]
		return dict(
			at=version["creation"], version=version["name"], actor=version.get("owner"), deadline=deadline
		)
	return None


def backfill_submission_events():
	ensure_submission_tracking()
	if frappe.db.get_default("dinext_submission_history_backfilled_v1"):
		return
	deleted_parents = set()
	uncertain_deletion = False
	# A removed position prevents proving the complete historical composition.
	for row in frappe.get_all(
		"Deleted Document", filters={"deleted_doctype": "User Timesheet Position"}, fields=["data"]
	):
		try:
			data = json.loads(row.data or "{}")
			if isinstance(data, dict) and data.get("user_timesheet"):
				deleted_parents.add(data["user_timesheet"])
			else:
				uncertain_deletion = True
		except (TypeError, ValueError):
			uncertain_deletion = True
	recovered = unknown = 0
	for name in frappe.get_all("User Timesheet", pluck="name"):
		if frappe.db.exists("Timesheet Submission Event", {"timesheet": name, "first_submission": 1}):
			continue
		if uncertain_deletion or name in deleted_parents:
			unknown += 1
			continue
		versions = frappe.get_all(
			"Version",
			filters={"ref_doctype": "User Timesheet", "docname": name},
			fields=["name", "creation", "owner", "data"],
			order_by="creation asc",
		)
		if not versions:
			unknown += 1
			continue
		positions = frappe.get_all(
			"User Timesheet Position", filters={"user_timesheet": name}, fields=["name", "creation"]
		)
		names = [row.name for row in positions]
		tasks = (
			frappe.get_all(
				"Workflow Task",
				filters={"reference_doctype": "User Timesheet Position", "reference_name": ["in", names]},
				fields=["reference_name", "workflow_state", "creation"],
				order_by="creation asc",
			)
			if names
			else []
		)
		parent = frappe.get_doc("User Timesheet", name)
		evidence = proven_submission(versions, positions, tasks, current_deadline=parent.ts_date_of_dispatch)
		if not evidence:
			unknown += 1
			continue
		record_submission(
			parent,
			event_key="version:" + evidence["version"],
			submitted_at=evidence["at"],
			historical_deadline=evidence["deadline"],
			actor=evidence["actor"],
			evidence="Version " + evidence["version"],
		)
		recovered += 1
	frappe.db.set_default("dinext_submission_history_backfilled_v1", 1)
	return dict(recovered=recovered, unknown=unknown)
