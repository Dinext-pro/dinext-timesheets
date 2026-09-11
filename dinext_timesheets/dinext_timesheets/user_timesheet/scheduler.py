"""Weekly User Timesheet auto-create (ISS-2026-00926 phase 2 F).

Port of demodev Scheduler Event ``TSCrW2`` (cron ``30 8 * * 1``).
Active demodev body = first block (overlap checks); trailing quoted legacy ignored.
"""

from __future__ import annotations

import frappe
from frappe.utils import add_days, get_last_day, getdate

logger = frappe.logger("user_timesheet")


def create_weekly_timesheets(dry_run: bool = False):
	"""Create weekly UT for Workers on auto weekly Timesheet Templates.

	Returns dict with created/skipped/would_create lists.
	When dry_run=True — no inserts.
	"""
	# bench execute may pass dry_run as str
	if isinstance(dry_run, str):
		dry_run = dry_run.lower() in ("1", "true", "yes")

	result = {"created": [], "skipped": [], "would_create": [], "dry_run": dry_run}

	timesheet_templates = frappe.get_list(
		"Timesheet Template",
		filters={"automatically": 1, "ttreporting_period": "Недельный"},
	)
	if not timesheet_templates:
		logger.info("TSCrW2: no auto weekly templates")
		return result

	current_date = getdate()
	week_start = current_date
	week_end = add_days(current_date, 6)

	for template in timesheet_templates:
		workers = frappe.get_all(
			"Worker",
			filters={"wtimesheet_template": template.name},
			fields=["name", "wuser", "wvalid_from", "wvalid_for"],
		)
		if not workers:
			continue

		filtered_workers = []
		for worker in workers:
			if not worker.wuser:
				continue
			if not frappe.db.get_value("User", worker.wuser, "enabled"):
				continue
			if worker.wvalid_for:
				wvalid_for = getdate(worker.wvalid_for)
				if wvalid_for < week_start:
					result["skipped"].append(
						{"worker": worker.name, "reason": "expired", "date": str(wvalid_for)}
					)
					continue
			filtered_workers.append(worker)

		if not filtered_workers:
			continue

		template_ref = frappe.get_doc("Timesheet Template", template.name)
		working_days = template_ref.working_days

		for worker in filtered_workers:
			worker_doc = frappe.get_doc("Worker", worker.name)
			valid_from = week_start
			valid_for = week_end

			if worker.wvalid_from:
				wvalid_from = getdate(worker.wvalid_from)
				if wvalid_from > week_end:
					result["skipped"].append(
						{"worker": worker.name, "reason": "starts_after_week"}
					)
					continue
				if wvalid_from > week_start:
					valid_from = wvalid_from

			if worker.wvalid_for:
				wvalid_for = getdate(worker.wvalid_for)
				if wvalid_for < week_start:
					continue
				if wvalid_for < week_end:
					valid_for = wvalid_for

			if valid_from > valid_for:
				result["skipped"].append(
					{"worker": worker.name, "reason": "invalid_dates"}
				)
				continue

			existing_timesheets = frappe.get_all(
				"User Timesheet",
				filters={
					"timesheet_from": worker_doc.wuser,
					"ts_valid_from": ["<=", valid_for],
					"ts_valid_for": [">=", valid_from],
				},
				fields=["name", "ts_valid_from", "ts_valid_for"],
			)
			if existing_timesheets:
				result["skipped"].append(
					{
						"worker": worker.name,
						"reason": "overlap",
						"existing": [e.name for e in existing_timesheets],
					}
				)
				continue

			end_of_month = get_last_day(current_date)
			periods = []

			vf, vt = valid_from, valid_for
			if end_of_month < vt:
				second_from = add_days(end_of_month, 1)
				second_to = vt
				periods.append((second_from, second_to))
				vt = end_of_month
			periods.append((vf, vt))

			for p_from, p_to in periods:
				if p_from > p_to:
					continue
				payload = {
					"worker": worker.name,
					"user": worker_doc.wuser,
					"template": template.name,
					"from": str(p_from),
					"to": str(p_to),
				}
				exists = frappe.db.exists(
					"User Timesheet",
					{
						"timesheet_from": worker_doc.wuser,
						"ts_valid_from": p_from,
						"ts_valid_for": p_to,
					},
				)
				if exists:
					result["skipped"].append({**payload, "reason": "exists"})
					continue

				if dry_run:
					result["would_create"].append(payload)
					continue

				timesheet = frappe.new_doc("User Timesheet")
				timesheet.timesheet_from = worker_doc.wuser
				timesheet.ts_from_template = template.name
				timesheet.ts_valid_from = p_from
				timesheet.ts_valid_for = p_to
				timesheet.ts_date_of_dispatch = add_days(p_to, working_days)
				timesheet.insert()
				result["created"].append({**payload, "name": timesheet.name})

	if not dry_run:
		frappe.db.commit()
	return result
