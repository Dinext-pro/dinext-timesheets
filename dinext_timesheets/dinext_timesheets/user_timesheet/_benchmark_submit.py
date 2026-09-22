"""Rollback-only baseline for User Timesheet submission performance.

Run only on the local dev site:

	bench --site dev.dinext.localhost execute \
	  dinext_timesheets.dinext_timesheets.user_timesheet._benchmark_submit.run
"""

from __future__ import annotations

import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from statistics import median
from time import perf_counter
from typing import Any, Callable

import frappe

from project_workload_assignment.project_workload_assignment.work_efforts.timesheet_limits.calculator import (
	TimesheetLimitsCalculator,
)

from .status import set_timesheet_status


SITE = "dev.dinext.localhost"
SCENARIOS = [
	{
		"label": "small",
		"timesheet": "Руслан Салагаев - 2026-07-20 - 2026-07-26",
	},
	{
		"label": "medium",
		"timesheet": "Руслан Салагаев - 2026-06-08 - 2026-06-14",
	},
	{
		"label": "large",
		"timesheet": "Руслан Салагаев - 2026-06-01 - 2026-06-07",
	},
]
RESULT_PATH = Path(__file__).with_name("_benchmark_submit_baseline.json")


def run(write_result: bool = True, repeats: int = 3) -> dict[str, Any]:
	"""Measure limits + status transition, rolling back every scenario."""
	if frappe.local.site != SITE:
		frappe.throw(f"Benchmark is restricted to {SITE}")
	repeats = max(1, int(repeats))

	result = {
		"site": SITE,
		"measured_at": str(frappe.utils.now_datetime()),
		"rollback_only": True,
		"scope": "limits pre-check + set_timesheet_status; excludes browser reload",
		"repeats": repeats,
		"scenarios": [_run_repeated_scenario(item, repeats) for item in SCENARIOS],
	}
	if write_result:
		RESULT_PATH.write_text(
			json.dumps(result, ensure_ascii=False, indent=2) + "\n",
			encoding="utf-8",
		)
	return result


def _run_repeated_scenario(
	scenario: dict[str, str], repeats: int
) -> dict[str, Any]:
	runs = [_run_scenario(scenario) for _ in range(repeats)]
	return {
		"label": scenario["label"],
		"timesheet": scenario["timesheet"],
		"profile": runs[0]["profile"],
		"summary": {
			"limits_median_ms": median(run["limits"]["wall_ms"] for run in runs),
			"status_median_ms": median(
				run["set_timesheet_status"]["wall_ms"] for run in runs
			),
			"combined_median_ms": median(run["combined_wall_ms"] for run in runs),
			"all_responses_equal": all(
				run["set_timesheet_status"]["response"]
				== runs[0]["set_timesheet_status"]["response"]
				for run in runs
			),
			"all_rollbacks_verified": all(
				run["rollback_verified"] for run in runs
			),
		},
		"runs": [
			{key: value for key, value in run.items() if key not in {"label", "timesheet", "profile"}}
			for run in runs
		],
	}


def _run_scenario(scenario: dict[str, str]) -> dict[str, Any]:
	frappe.db.rollback()
	timesheet_name = scenario["timesheet"]
	before = _snapshot(timesheet_name)
	original_user = frappe.session.user
	original_in_test = getattr(frappe.flags, "in_test", False)
	original_commit = frappe.db.commit

	try:
		_prepare_start_state(timesheet_name, before["position_names"])
		frappe.set_user(before["owner"])
		frappe.flags.in_test = True

		def blocked_commit(*args, **kwargs):
			raise RuntimeError("Explicit commit is forbidden inside rollback benchmark")

		frappe.db.commit = blocked_commit

		payload = _limits_payload(timesheet_name)
		limits = _measure(
			lambda: TimesheetLimitsCalculator.run(
				frappe._dict(
					{
						"positions": payload,
						"timesheet_name": timesheet_name,
					}
				)
			)
		)
		_compact_limits_response(limits)
		effects_before = _effect_counts(before["position_names"])
		status = (
			_measure(
				lambda: set_timesheet_status(
					positions=before["position_names"],
					pos_status="На согласовании",
					ts_name=timesheet_name,
					ts_status="На согласовании",
				)
			)
			if limits["ok"]
			else {"ok": False, "skipped": "limits failed", "wall_ms": 0}
		)
		effects_after = _effect_counts(before["position_names"])
		transient_state = _snapshot(timesheet_name)
	finally:
		frappe.db.commit = original_commit
		frappe.flags.in_test = original_in_test
		frappe.set_user(original_user)
		frappe.db.rollback()

	after = _snapshot(timesheet_name)
	rollback_verified = (
		before["ut_status"] == after["ut_status"]
		and before["position_states"] == after["position_states"]
		and before["working_workflow_tasks"] == after["working_workflow_tasks"]
	)

	return {
		"label": scenario["label"],
		"timesheet": timesheet_name,
		"profile": {
			"period_days": before["period_days"],
			"positions": len(before["position_names"]),
			"projects": before["projects"],
			"hours": before["hours"],
			"owner": before["owner"],
		},
		"normalized_setup": {
			"ut_status": "Черновик",
			"position_status": "Редактирование",
			"existing_working_workflow_tasks": "temporarily cancelled",
		},
		"limits": limits,
		"set_timesheet_status": status,
		"combined_wall_ms": round(limits["wall_ms"] + status["wall_ms"], 1),
		"transient_effects": {
			key: effects_after[key] - effects_before[key] for key in effects_after
		},
		"transient_result_state": {
			"ut_status": transient_state["ut_status"],
			"position_statuses": transient_state["position_status_counts"],
			"working_workflow_tasks": transient_state["working_workflow_tasks"],
		},
		"rollback_verified": rollback_verified,
	}


def _compact_limits_response(measurement: dict[str, Any]) -> None:
	response = measurement.get("response")
	if not isinstance(response, list):
		return
	statuses: dict[str, int] = {}
	for row in response:
		status = row.get("status") or ""
		statuses[status] = statuses.get(status, 0) + 1
	measurement["response"] = {
		"rows": len(response),
		"statuses": statuses,
	}


def _prepare_start_state(timesheet_name: str, position_names: list[str]) -> None:
	frappe.db.sql(
		"""
		UPDATE `tabUser Timesheet`
		SET ut_status = 'Черновик'
		WHERE name = %s
		""",
		timesheet_name,
	)
	frappe.db.sql(
		"""
		UPDATE `tabUser Timesheet Position`
		SET status = 'Редактирование', workflow_state = 'Редактирование'
		WHERE user_timesheet = %s
		""",
		timesheet_name,
	)
	frappe.db.sql(
		"""
		UPDATE `tabWorkflow Task`
		SET status = 'Cancelled'
		WHERE doc = 'User Timesheet Position'
		  AND wt_docname IN %s
		  AND status = 'Working'
		""",
		[tuple(position_names)],
	)
	frappe.clear_document_cache("User Timesheet", timesheet_name)
	for position_name in position_names:
		frappe.clear_document_cache("User Timesheet Position", position_name)


def _limits_payload(timesheet_name: str) -> list[dict[str, Any]]:
	return frappe.get_all(
		"User Timesheet Position",
		filters={"user_timesheet": timesheet_name},
		fields=[
			"name",
			"document_name",
			"project_role",
			"project",
			"status",
			"all_hours",
			"custom_username",
		],
		order_by="name",
	)


def _measure(function: Callable[[], Any]) -> dict[str, Any]:
	original_sql = frappe.db.sql
	sql_times: list[float] = []
	captured_output = StringIO()

	def counted_sql(*args, **kwargs):
		started = perf_counter()
		try:
			return original_sql(*args, **kwargs)
		finally:
			sql_times.append(perf_counter() - started)

	frappe.db.sql = counted_sql
	started = perf_counter()
	try:
		with redirect_stdout(captured_output):
			response = function()
		return {
			"ok": True,
			"wall_ms": round((perf_counter() - started) * 1000, 1),
			"sql_count": len(sql_times),
			"sql_ms": round(sum(sql_times) * 1000, 1),
			"captured_log_chars": len(captured_output.getvalue()),
			"response": _jsonable(response),
		}
	except Exception as exc:
		return {
			"ok": False,
			"wall_ms": round((perf_counter() - started) * 1000, 1),
			"sql_count": len(sql_times),
			"sql_ms": round(sum(sql_times) * 1000, 1),
			"captured_log_chars": len(captured_output.getvalue()),
			"response": {
				"exception": type(exc).__name__,
				"message": str(exc),
			},
		}
	finally:
		frappe.db.sql = original_sql


def _snapshot(timesheet_name: str) -> dict[str, Any]:
	timesheet = frappe.db.get_value(
		"User Timesheet",
		timesheet_name,
		["timesheet_from", "ut_status", "ts_valid_from", "ts_valid_for"],
		as_dict=True,
	)
	if not timesheet:
		frappe.throw(f"User Timesheet not found: {timesheet_name}")

	positions = frappe.get_all(
		"User Timesheet Position",
		filters={"user_timesheet": timesheet_name},
		fields=["name", "project", "status", "workflow_state", "all_hours"],
		order_by="name",
	)
	position_names = [row.name for row in positions]
	status_counts: dict[str, int] = {}
	for row in positions:
		key = row.status or ""
		status_counts[key] = status_counts.get(key, 0) + 1

	return {
		"owner": timesheet.timesheet_from,
		"ut_status": timesheet.ut_status,
		"period_days": frappe.utils.date_diff(
			timesheet.ts_valid_for, timesheet.ts_valid_from
		)
		+ 1,
		"position_names": position_names,
		"position_states": [
			(row.name, row.status or "", row.workflow_state or "") for row in positions
		],
		"position_status_counts": status_counts,
		"projects": len({row.project for row in positions if row.project}),
		"hours": sum(frappe.utils.flt(row.all_hours) for row in positions),
		"working_workflow_tasks": _working_workflow_tasks(position_names),
	}


def _working_workflow_tasks(position_names: list[str]) -> int:
	if not position_names:
		return 0
	return frappe.db.count(
		"Workflow Task",
		{
			"doc": "User Timesheet Position",
			"wt_docname": ["in", position_names],
			"status": "Working",
		},
	)


def _effect_counts(position_names: list[str]) -> dict[str, int]:
	workflow_tasks = frappe.get_all(
		"Workflow Task",
		filters={
			"doc": "User Timesheet Position",
			"wt_docname": ["in", position_names],
			"status": "Working",
		},
		pluck="name",
	)
	return {
		"workflow_tasks": len(workflow_tasks),
		"todos": _count_linked("ToDo", "reference_type", "reference_name", workflow_tasks),
		"docshares": _count_linked(
			"DocShare", "share_doctype", "share_name", workflow_tasks
		),
		"comments": frappe.db.count(
			"Comment",
			{
				"reference_doctype": "User Timesheet Position",
				"reference_name": ["in", position_names],
			},
		),
		"email_queue": frappe.db.count("Email Queue"),
		"notification_logs": frappe.db.count("Notification Log"),
	}


def _count_linked(
	doctype: str,
	type_field: str,
	name_field: str,
	names: list[str],
) -> int:
	if not names:
		return 0
	return frappe.db.count(
		doctype,
		{
			type_field: "Workflow Task",
			name_field: ["in", names],
		},
	)


def _jsonable(value: Any) -> Any:
	if hasattr(value, "as_dict"):
		return value.as_dict()
	if isinstance(value, (str, int, float, bool)) or value is None:
		return value
	if isinstance(value, dict):
		return {key: _jsonable(item) for key, item in value.items()}
	if isinstance(value, (list, tuple)):
		return [_jsonable(item) for item in value]
	return str(value)
