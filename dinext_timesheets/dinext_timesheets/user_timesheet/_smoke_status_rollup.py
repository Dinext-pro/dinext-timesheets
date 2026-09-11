"""One-shot status rollup smoke (ISS-2026-00926 phase 2). Temp docs + cleanup."""

from __future__ import annotations

import frappe
from frappe.utils import add_days, getdate

from dinext_timesheets.dinext_timesheets.user_timesheet.events import hours as hours_mod
from dinext_timesheets.dinext_timesheets.user_timesheet.events import journal
from dinext_timesheets.dinext_timesheets.user_timesheet.events.status_rollup import (
	rollup_ut_status_and_task_dates,
)


def run():
	orig_je = journal.maybe_create_or_cancel_journal_entries
	orig_hours = hours_mod.calculate_ut_hours
	journal.maybe_create_or_cancel_journal_entries = lambda *a, **k: None
	hours_mod.calculate_ut_hours = lambda doc: None

	ut_name = None
	utps = []
	try:
		worker = frappe.get_all(
			"Worker",
			filters={"wuser": ["like", "%@%"], "wtimesheet_template": ["!=", ""]},
			fields=["name", "wuser", "wtimesheet_template"],
			limit=1,
		)
		if not worker:
			print("SMOKE_FAIL no worker")
			return
		w = worker[0]

		# inside Holiday List 2025-01-01..2026-12-31
		valid_from = getdate("2026-12-07")
		valid_for = add_days(valid_from, 6)

		ut = frappe.get_doc(
			{
				"doctype": "User Timesheet",
				"timesheet_from": w.wuser,
				"ts_from_template": w.wtimesheet_template,
				"ts_valid_from": valid_from,
				"ts_valid_for": valid_for,
				"ut_status": "Черновик",
			}
		)
		ut.insert(ignore_permissions=True)
		ut_name = ut.name
		print("created_ut", ut_name)

		task = frappe.get_all("Task", fields=["name", "project"], limit=1)
		if not task:
			print("SMOKE_FAIL no task")
			return
		t = task[0]

		role = None
		meta = frappe.get_meta("User Timesheet Position")
		if meta.has_field("project_role"):
			role = frappe.db.get_value(
				"Project Team Details", {"parent": t.project}, "pt_role"
			) or frappe.db.get_value("Project Role", {}, "name")

		def _new_utp():
			d = frappe.get_doc(
				{
					"doctype": "User Timesheet Position",
					"user_timesheet": ut_name,
					"user": w.wuser,
					"document_type": "Task",
					"document_name": t.name,
					"project": t.project,
					"status": "Редактирование",
					"workflow_state": "Редактирование",
				}
			)
			if role:
				d.project_role = role
			d.insert(ignore_permissions=True)
			return d

		utp1 = _new_utp()
		utp2 = _new_utp()
		utps = [utp1.name, utp2.name]
		print("created_utp", utps)

		results = {}

		doc = frappe.get_doc("User Timesheet Position", utp1.name)
		before = frappe.get_doc("User Timesheet Position", utp1.name)
		before.status = "Редактирование"
		doc.status = "Отклонено"
		doc.workflow_state = "Отклонено"
		doc._doc_before_save = before
		rollup_ut_status_and_task_dates(doc)
		ut.reload()
		results["reject"] = ut.ut_status
		print("after_reject", ut.ut_status)

		frappe.db.set_value("User Timesheet", ut_name, "ut_status", "Черновик")
		frappe.db.set_value(
			"User Timesheet Position",
			utp1.name,
			{"status": "Редактирование", "workflow_state": "Редактирование"},
		)

		frappe.db.set_value("User Timesheet", ut_name, "ut_status", "На согласовании")
		frappe.db.set_value(
			"User Timesheet Position",
			utp1.name,
			{"status": "На согласовании", "workflow_state": "На согласовании"},
		)
		doc = frappe.get_doc("User Timesheet Position", utp1.name)
		before = frappe.get_doc("User Timesheet Position", utp1.name)
		before.status = "На согласовании"
		doc.status = "Редактирование"
		doc.workflow_state = "Редактирование"
		doc._doc_before_save = before
		rollup_ut_status_and_task_dates(doc)
		ut.reload()
		results["rework"] = ut.ut_status
		print("after_rework", ut.ut_status)

		frappe.db.set_value(
			"User Timesheet Position",
			utp1.name,
			{"status": "Согласовано", "workflow_state": "Согласовано"},
		)
		frappe.db.set_value(
			"User Timesheet Position",
			utp2.name,
			{"status": "Согласовано", "workflow_state": "Согласовано"},
		)
		frappe.db.set_value("User Timesheet", ut_name, "ut_status", "На согласовании")
		doc = frappe.get_doc("User Timesheet Position", utp2.name)
		before = frappe.get_doc("User Timesheet Position", utp2.name)
		before.status = "На согласовании"
		doc.status = "Согласовано"
		doc._doc_before_save = before
		rollup_ut_status_and_task_dates(doc)
		ut.reload()
		results["approve_all"] = ut.ut_status
		print("after_approve_all", ut.ut_status, "approval_date", ut.ut_approval_date)

		ok = (
			results.get("reject") == "Отклонено"
			and results.get("rework") == "На доработке"
			and results.get("approve_all") == "Согласован"
		)
		print("SMOKE_STATUS_ROLLUP", "PASS" if ok else "FAIL", results)
	finally:
		_cleanup(ut_name, utps)
		journal.maybe_create_or_cancel_journal_entries = orig_je
		hours_mod.calculate_ut_hours = orig_hours
		frappe.db.commit()


def _cleanup(ut_name, utps):
	for name in utps or []:
		if name and frappe.db.exists("User Timesheet Position", name):
			frappe.delete_doc(
				"User Timesheet Position", name, ignore_permissions=True, force=1
			)
	if ut_name and frappe.db.exists("User Timesheet", ut_name):
		frappe.delete_doc("User Timesheet", ut_name, ignore_permissions=True, force=1)
	print("cleaned", ut_name, utps)
