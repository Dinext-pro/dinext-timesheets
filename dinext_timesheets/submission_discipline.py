"""First complete Timesheet submission, kept separate from approval discipline."""

import hashlib
import json
from collections import defaultdict

import frappe
from frappe.utils import get_system_timezone, getdate, now_datetime, nowdate

TRACKING_KEY = "dinext_timesheet_submission_tracking_started_at"


def ensure_submission_tracking():
	if not frappe.db.get_default(TRACKING_KEY):
		frappe.db.set_default(TRACKING_KEY, now_datetime())


def submission_result(events, *, today, current_deadline, current_status="Draft", history_tracked=True):
	first = next(
		(
			row
			for row in sorted(events, key=lambda row: str(row["submitted_at"]))
			if row.get("first_submission")
		),
		None,
	)
	if first:
		actual = first["submitted_at"]
		deadline = first.get("submission_deadline")
		actual_date = first.get("submitted_local_date") or str(actual)[:10]
		status = (
			("On Time" if str(actual_date)[:10] <= str(deadline)[:10] else "Completed Late")
			if deadline
			else "Unknown"
		)
	else:
		actual = None
		deadline = current_deadline
		status = (
			("Overdue" if deadline and str(deadline)[:10] < str(today)[:10] else "Pending")
			if history_tracked
			and current_status in ("Draft", "Rework", "Rejected", "Черновик", "На доработке", "Отклонено")
			else "Unknown"
		)
	return dict(
		status=status,
		actual=actual,
		deadline=deadline,
		resubmissions=sum(not row.get("first_submission") for row in events),
	)


def record_submission(
	parent, *, event_key, submitted_at=None, evidence="Workflow", historical_deadline=None, actor=None
):
	"""Caller has established a complete submission; lock parent for the first-event invariant."""
	parent = frappe.get_doc("User Timesheet", parent.name, for_update=True)
	key = hashlib.sha256((parent.name + "\0" + event_key).encode()).hexdigest()
	if frappe.db.exists("Timesheet Submission Event", key):
		return
	first = not frappe.db.exists(
		"Timesheet Submission Event", {"timesheet": parent.name, "first_submission": 1}
	)
	tracking_start = frappe.db.get_default(TRACKING_KEY)
	first = first and (
		evidence.startswith("Version ")
		or bool(tracking_start and str(parent.creation) >= str(tracking_start))
	)
	from dinext_common.workflow_approval.notifications import _aware_utc, get_timezone

	submitted_at = submitted_at or now_datetime()
	timezone_name = get_system_timezone()
	frappe.get_doc(
		dict(
			doctype="Timesheet Submission Event",
			event_key=key,
			timesheet=parent.name,
			submitted_at=submitted_at,
			submitted_by=actor or frappe.session.user,
			submission_timezone=timezone_name,
			submitted_local_date=_aware_utc(submitted_at).astimezone(get_timezone(timezone_name)).date(),
			submission_deadline=historical_deadline
			if evidence.startswith("Version ")
			else parent.ts_date_of_dispatch,
			first_submission=int(first),
			evidence=evidence,
		)
	).insert(ignore_permissions=True)


def on_timesheet_update(parent, method=None):
	old = parent.get_doc_before_save()
	if not old or old.ut_status == parent.ut_status:
		return
	if parent.ut_status not in ("Pending Approval", "Approved", "На согласовании", "Согласован"):
		return
	if old.ut_status not in ("Draft", "Rework", "Rejected", "Черновик", "На доработке", "Отклонено"):
		return
	maybe_record_complete(parent)


def maybe_record_complete(parent):
	parent = frappe.get_doc("User Timesheet", parent.name, for_update=True)
	if parent.ut_status not in ("Pending Approval", "Approved", "На согласовании", "Согласован"):
		return
	positions = frappe.get_all(
		"User Timesheet Position",
		filters={"user_timesheet": parent.name},
		fields=["name", "status", "workflow_state", "modified"],
		order_by="name asc",
	)
	accepted = {"Pending Approval", "Approved", "На согласовании", "Согласован"}
	if any((row.status or row.workflow_state) not in accepted for row in positions):
		return
	identity = (
		json.dumps([(row.name, str(row.modified)) for row in positions], ensure_ascii=False)
		if positions
		else str(parent.modified)
	)
	record_submission(parent, event_key="complete:" + identity, evidence="Complete parent and positions")


def visible_data(filters=None):
	from dinext_common.workflow_approval.deadlines.discipline import _candidate_rows
	from dinext_common.workflow_approval.deadlines.discipline import metrics as approval_metrics

	filters = filters or {}
	query = {}
	if filters.get("author"):
		query["timesheet_from"] = filters["author"]
	if filters.get("timesheet"):
		query["name"] = filters["timesheet"]
	start = getdate(filters.get("from_date") or frappe.utils.add_days(nowdate(), -29))
	end = getdate(filters.get("to_date") or nowdate())
	approval_filters = {
		"reference_doctype": "User Timesheet Position",
		**{key: filters[key] for key in ("from_date", "to_date", "approver") if filters.get(key)},
	}
	# Discover candidate parents from bounded current/cohort task references only.
	# No task metric is evaluated until permitted parents have been established.
	candidates = (
		_candidate_rows(approval_filters, ["reference_name"])
		if frappe.has_permission("Workflow Task", "read")
		else []
	)
	position_names = list({row.reference_name for row in candidates})
	approval_parents = (
		set(
			frappe.get_all(
				"User Timesheet Position", filters={"name": ["in", position_names]}, pluck="user_timesheet"
			)
		)
		if position_names
		else set()
	)
	first_parents = frappe.get_all(
		"Timesheet Submission Event",
		filters={"first_submission": 1, "submission_deadline": ["between", [str(start), str(end)]]},
		pluck="timesheet",
	)
	cohort_parents = approval_parents | set(first_parents)
	parent_scope = [["ts_date_of_dispatch", "between", [str(start), str(end)]]]
	parent_scope.append(
		[
			"ut_status",
			"in",
			[
				"Draft",
				"Rework",
				"Rejected",
				"Pending Approval",
				"Черновик",
				"На доработке",
				"Отклонено",
				"На согласовании",
			],
		]
	)
	if cohort_parents:
		parent_scope.append(["name", "in", list(cohort_parents)])
	parents = frappe.get_list(
		"User Timesheet",
		filters=query,
		or_filters=parent_scope,
		fields=[
			"name",
			"timesheet_from",
			"timesheet_from_name",
			"ts_valid_from",
			"ts_valid_for",
			"ts_date_of_dispatch",
			"ut_status",
			"creation",
		],
		limit_page_length=0,
	)
	from dinext_common.workflow_approval.permissions import _batch_read_helper

	batch_read = _batch_read_helper()
	if batch_read:
		permitted = batch_read("User Timesheet", [row.name for row in parents])
		parents = [row for row in parents if row.name in permitted]
	else:
		parents = [
			row for row in parents if frappe.get_doc("User Timesheet", row.name).has_permission("read")
		]
	names = {row.name for row in parents}

	events = defaultdict(list)
	if names:
		# Internal event storage is readable only through a permitted parent.
		for row in frappe.get_all(
			"Timesheet Submission Event",
			filters={"timesheet": ["in", names]},
			fields=[
				"timesheet",
				"submitted_at",
				"submitted_local_date",
				"submission_deadline",
				"first_submission",
			],
			order_by="submitted_at asc",
		):
			events[row.timesheet].append(dict(row))
	# Author and source permissions narrow the approval query before task reads.
	position_map = (
		{
			row.name: row
			for row in frappe.get_all(
				"User Timesheet Position",
				filters={"user_timesheet": ["in", list(names)]},
				fields=["name", "user_timesheet", "all_hours"],
			)
		}
		if names
		else {}
	)
	approvals = (
		approval_metrics({**approval_filters, "reference_name": ["in", list(position_map)]})
		if position_map
		else {"all_rows": []}
	)

	by_parent = defaultdict(list)
	for row in approvals["all_rows"]:
		position = position_map.get(row["reference_name"])
		if position and position.user_timesheet in names:
			by_parent[position.user_timesheet].append(row)
	data = []
	tracking_start = frappe.db.get_default(TRACKING_KEY)
	for parent in parents:
		result = submission_result(
			events[parent.name],
			today=nowdate(),
			current_deadline=parent.ts_date_of_dispatch,
			current_status=parent.ut_status,
			history_tracked=bool(tracking_start and str(parent.creation) >= str(tracking_start)),
		)
		submission_in_period = bool(result["deadline"] and start <= getdate(result["deadline"]) <= end)
		assignments = by_parent[parent.name]
		cohort = [
			row
			for row in assignments
			if row["due_date"]
			and start <= row["due_date"] <= end
			and row["discipline_status"] in ("On Time", "Completed Late", "Overdue")
		]
		eligible = len(cohort)
		ontime = sum(row["discipline_status"] == "On Time" for row in cohort)
		overdue = {row["reference_name"] for row in assignments if row["discipline_status"] == "Overdue"}
		pending = {row["reference_name"] for row in assignments if row["status"] == "Working"}
		data.append(
			dict(
				timesheet=parent.name,
				author=parent.timesheet_from,
				author_name=parent.timesheet_from_name,
				period_from=parent.ts_valid_from,
				period_to=parent.ts_valid_for,
				submission_deadline=result["deadline"],
				submitted_at=result["actual"],
				submission_status=result["status"],
				resubmissions=result["resubmissions"],
				submission_in_period=submission_in_period,
				approval_observations=eligible,
				approval_on_time=ontime,
				approval_percent=100 * ontime / eligible if eligible else None,
				overdue_positions=len(overdue),
				overdue_timesheet=int(bool(overdue)),
				pending_hours=sum(float(position_map[name].all_hours or 0) for name in pending),
			)
		)
	return data


def summary(filters=None):
	rows = visible_data(filters)
	known = [
		row
		for row in rows
		if row["submission_in_period"]
		and row["submission_status"] in ("On Time", "Completed Late", "Overdue")
	]
	approval_count = sum(row["approval_observations"] for row in rows)
	return dict(
		rows=rows,
		submission_percent=100 * sum(row["submission_status"] == "On Time" for row in known) / len(known)
		if known
		else None,
		approval_percent=100 * sum(row["approval_on_time"] for row in rows) / approval_count
		if approval_count
		else None,
		overdue_timesheets=sum(row["overdue_timesheet"] for row in rows),
		overdue_positions=sum(row["overdue_positions"] for row in rows),
		pending_hours=sum(row["pending_hours"] for row in rows),
	)


def _card(key, *, percent=False):
	if frappe.session.user == "Guest":
		raise frappe.PermissionError
	result = summary({"author": frappe.session.user})
	return dict(
		value=round(result[key], 1) if result[key] is not None else None,
		fieldtype="Percent" if percent else "Float",
		route=["query-report", "Timesheet Deadline Discipline"],
		route_options={"author": frappe.session.user},
	)


@frappe.whitelist()
def submission_card():
	return _card("submission_percent", percent=True)


@frappe.whitelist()
def approval_card():
	return _card("approval_percent", percent=True)


@frappe.whitelist()
def overdue_timesheets_card():
	return _card("overdue_timesheets")


@frappe.whitelist()
def overdue_positions_card():
	return _card("overdue_positions")


@frappe.whitelist()
def pending_hours_card():
	return _card("pending_hours")
