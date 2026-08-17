"""User Timesheet Position doc_events (ISS-2026-00926 phase 2)."""

from __future__ import annotations

from .hours import calculate_utp_all_hours
from .limits_notify import notify_task_limit_exceeded
from .ownership import set_utp_owner_from_user, set_utp_period, set_utp_user_group
from .status_rollup import rollup_ut_status_and_task_dates
from .utilization import apply_utilization_hours
from .workflow_tasks import (
	delete_linked_workflow_tasks,
	process_workflow_tasks_after_save,
	process_workflow_tasks_before_save,
)


def before_insert(doc, method=None):
	set_utp_owner_from_user(doc)
	set_utp_period(doc)


def before_save(doc, method=None):
	# Block B WT before ownership/hours (status may change via workflow).
	process_workflow_tasks_before_save(doc)
	set_utp_user_group(doc)
	apply_utilization_hours(doc)
	calculate_utp_all_hours(doc)


def on_update(doc, method=None):
	# Demodev SS event label "After Save" → Document.on_update
	process_workflow_tasks_after_save(doc)
	rollup_ut_status_and_task_dates(doc)
	notify_task_limit_exceeded(doc)


def on_trash(doc, method=None):
	# Demodev SS: Before Delete → Frappe hook on_trash
	delete_linked_workflow_tasks(doc)
