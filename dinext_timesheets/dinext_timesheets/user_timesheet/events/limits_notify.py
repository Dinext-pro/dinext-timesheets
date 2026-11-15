"""Send limit notices for committed entries into position approval."""

from __future__ import annotations

import hashlib
import json

import frappe
from frappe.core.doctype.server_script.server_script_utils import get_server_script_map
from frappe.utils import flt, get_datetime

from dinext_timesheets.timesheet_status import PENDING_POSITION_STATUSES

POSITION = "User Timesheet Position"


def schedule_limit_notice(position, round_id: str) -> None:
	if position.doctype == POSITION and position.status in PENDING_POSITION_STATUSES:
		frappe.enqueue(
			notify_task_limit_if_pending,
			position_name=position.name,
			source_created_at=str(get_datetime(position.creation)),
			round_id=round_id,
			queue="short",
			enqueue_after_commit=True,
		)


def notify_task_limit_exceeded(doc) -> None:
	"""Schedule the legacy notice only when the generic engine is inactive."""
	from dinext_timesheets.workflow_approval import _enabled

	if _enabled():
		return
	old_doc = doc.get_doc_before_save()
	if old_doc and old_doc.status not in PENDING_POSITION_STATUSES and doc.status in PENDING_POSITION_STATUSES:
		legacy_scripts = get_server_script_map().get(POSITION, {}).get("After Save", ())
		if "Task Limit Exceeded_V4" in legacy_scripts:
			return
		modified = str(get_datetime(doc.modified))
		identity = hashlib.sha256(f"{doc.name}\n{doc.creation}\n{modified}".encode()).hexdigest()
		frappe.enqueue(
			notify_task_limit_if_pending,
			position_name=doc.name,
			source_created_at=str(get_datetime(doc.creation)),
			legacy_modified=modified,
			queue="short",
			enqueue_after_commit=True,
			job_id=f"timesheet-limit-{identity}",
			deduplicate=True,
		)


def _lock_position(position_name: str):
	parent = frappe.db.get_value(POSITION, position_name, "user_timesheet")
	if not parent or not frappe.db.get_value("User Timesheet", parent, "name", for_update=True):
		return None
	try:
		position = frappe.get_doc(POSITION, position_name, for_update=True)
	except frappe.DoesNotExistError:
		return None
	return position if position.user_timesheet == parent else None


def _is_current_round(position, round_id: str) -> bool:
	return bool(frappe.db.exists("Workflow Task", {
		"approval_round_id": round_id,
		"reference_doctype": POSITION,
		"reference_name": position.name,
		"source_created_at": position.creation,
		"status": "Working",
		"round_status": "Open",
	}))


def _lock_round_ledger(position, round_id: str):
	return frappe.db.get_value("Workflow Task", {
		"approval_round_id": round_id,
		"reference_doctype": POSITION,
		"reference_name": position.name,
		"source_created_at": position.creation,
	}, ["name", "notification_delivery_snapshot"],
		as_dict=True, order_by="creation asc, name asc", for_update=True)


def notify_task_limit_if_pending(
	position_name: str,
	round_id: str | None = None,
	source_created_at: str | None = None,
	legacy_modified: str | None = None,
) -> None:
	"""Lock the committed source, then claim at most one notice per round and recipient."""
	position = _lock_position(position_name)
	if (
		not position
		or not source_created_at
		or str(get_datetime(position.creation)) != source_created_at
		or position.status not in PENDING_POSITION_STATUSES
	):
		return
	if round_id:
		if not _is_current_round(position, round_id):
			return
		ledger = _lock_round_ledger(position, round_id)
		if not ledger:
			return
		snapshot = frappe.parse_json(ledger.notification_delivery_snapshot or "{}")
	else:
		from dinext_timesheets.workflow_approval import _enabled

		if _enabled() or not legacy_modified or str(get_datetime(position.modified)) != legacy_modified:
			return
		ledger = None
		snapshot = {}
	notice = _limit_notice(position)
	if not notice:
		return
	config, recipients = notice
	delivered = set(snapshot.get("limit_notice_recipients", ()))
	for recipient in dict.fromkeys(recipients):
		if recipient not in delivered:
			_send_notice(position, config, recipient)
			delivered.add(recipient)
	if ledger and delivered != set(snapshot.get("limit_notice_recipients", ())):
		snapshot["limit_notice_recipients"] = sorted(delivered)
		frappe.db.set_value("Workflow Task", ledger.name, "notification_delivery_snapshot",
			frappe.as_json(snapshot), update_modified=False)


def _limit_notice(position):
	recipients = frappe.get_all("Project Team Details", filters={
		"parent": position.project,
		"notifications_on_limits": 1,
		"pt_participant_type": "User",
		"pt_participant": ("is", "set"),
	}, pluck="pt_participant")
	if not recipients:
		return None
	limit = frappe.db.get_value("Limit Control", {
		"parent": position.project, "type": "Уведомление", "view": "Notification",
	}, ["limit", "notification"], as_dict=True)
	if not limit or not limit.notification:
		return None
	positions = [{
		"document_name": position.document_name,
		"project_role": position.project_role,
		"project": position.project,
		"status": position.status,
	}]
	from project_workload_assignment import api

	calculate = getattr(api, "calculate_timesheet_limits_for", None)
	if calculate:
		rows = calculate(positions)
	else:
		# The older PWA exposes the same calculator through its original API.
		from frappe.utils.safe_exec import call_whitelisted_function

		rows = call_whitelisted_function(
			"project_workload_assignment.api.calculate_user_timesheet_limits",
			positions=json.dumps(positions),
		) or frappe.response.get("message")
	if not rows or (planned := flt(rows[0].get("planned_hours"))) <= 0:
		return None
	actual = flt(rows[0].get("total_hours"))
	percentage = actual / planned * 100
	if percentage <= limit.limit:
		return None
	return {
		"notification": limit.notification,
		"completion_percentage": percentage,
		"actual_hours": actual,
		"planned_hours": planned,
		"timesheet_position": position.name,
		"task_name": position.document_name,
		"project": position.project,
		"project_role": position.project_role,
	}, recipients


def _send_notice(position, config, recipient):
	notification = frappe.get_doc("Notification", config["notification"])
	todo = frappe.new_doc("ToDo")
	todo.description = frappe._("Timesheet limit exceeded")
	todo.allocated_to = recipient
	todo.reference_type = POSITION
	todo.reference_name = position.name
	todo.flags.context = {key: value for key, value in config.items() if key != "notification"}
	notification.send(todo)
