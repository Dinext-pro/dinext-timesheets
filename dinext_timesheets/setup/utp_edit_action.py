"""Refresh open UTP approval snapshots after renaming their editing action."""

import frappe
from frappe import _

from dinext_common.workflow_approval.policy import transition_semantic_hash

WORKFLOW = "UTP Workflow"
POSITION = "User Timesheet Position"
FORMER_ACTIONS = {"Stop Workflow", "Остановить Воркфлоу"}
PENDING_STATES = ("Pending Approval", "На согласовании")
EDITING_STATES = ("Editing", "Редактирование")


def _affected_rounds():
	fields = (
		"name", "approval_round_id", "reference_name", "round_status", "round_manifest", "status", "action",
		"transition_uuid",
	)
	if not frappe.db.table_exists("Workflow Task") or not {
		"workflow", "reference_doctype", "workflow_state", *fields,
	}.issubset(frappe.db.get_table_columns("Workflow Task")):
		return {}

	rounds = {}
	for task in frappe.get_all(
		"Workflow Task",
		filters={
			"workflow": WORKFLOW,
			"reference_doctype": POSITION,
			"workflow_state": ("in", PENDING_STATES),
			"round_status": ("in", ("Open", "Finalizing", "Stalled", "Conflicted")),
		},
		fields=list(fields),
	):
		rounds.setdefault(task.approval_round_id, []).append(task)

	affected = {}
	for round_id, tasks in rounds.items():
		retiring = {
			row.get("transition_uuid")
			for task in tasks
			for row in (frappe.parse_json(task.round_manifest) or {}).get("transitions", [])
			if row.get("action") in FORMER_ACTIONS
		}
		if retiring:
			affected[round_id] = (tasks, retiring)
	return affected


def _check_rounds(rounds):
	for round_id, (tasks, retiring) in rounds.items():
		retiring_ids = retiring - {None, ""}
		if any(
			task.round_status == "Finalizing"
			or (
				task.status == "Completed"
				and (task.action in FORMER_ACTIONS or task.transition_uuid in retiring_ids)
			)
			for task in tasks
		):
			frappe.throw(
				_("Resolve UTP approval round {0} before replacing Stop Workflow.").format(round_id)
			)


def guard_open_rounds():
	_check_rounds(_affected_rounds())


def prepare_workflow_import(doc, method=None):
	if not frappe.flags.in_fixtures or doc.document_type != POSITION:
		return
	if not frappe.db.exists("Workflow", doc.name):
		doc.workflow_state_field = "status"
		return
	# Frappe reimports fixtures by replacing the entire document and its child tables.
	# Keep the site's configured UTP schemes, including legacy sites awaiting cutover.
	doc.update(frappe.get_doc("Workflow", doc.name).as_dict())
	if doc.name != WORKFLOW:
		return
	previous = [
		row for row in doc.transitions
		if row.state in PENDING_STATES
		and row.next_state in EDITING_STATES
		and row.action in FORMER_ACTIONS | {"Edit"}
	]
	if not any(row.action in FORMER_ACTIONS for row in previous):
		return
	if len(previous) != 1:
		frappe.throw(_("Resolve the duplicate Pending Approval to Editing transitions before replacing Stop Workflow."))
	edit = previous[0]
	edit.action = "Edit"

	from dinext_common.workflow_approval.engine import _eligible_approvers, _transition_dict

	rounds = _affected_rounds()
	_check_rounds(rounds)
	_check_edit_identity(rounds, _transition_dict(edit))
	for name in _open_sources(rounds):
		if not _eligible_approvers(frappe.get_doc(POSITION, name), edit):
			frappe.throw(_("Position {0} has no eligible actor for Edit.").format(name))


def validate_position_state_field(doc, method=None):
	if doc.document_type != POSITION:
		return
	from dinext_timesheets.dinext_timesheets.user_timesheet.status import has_legacy_position_status

	if has_legacy_position_status():
		return
	if doc.workflow_state_field != "status":
		frappe.throw(_("Select status as the Workflow state field for User Timesheet Position."))
	if any(row.update_field == "status" and row.update_value != row.state for row in doc.states):
		frappe.throw(_("A User Timesheet Position Workflow state cannot set status to a different state."))


def _open_sources(rounds):
	return sorted({
		task.reference_name
		for tasks, _retiring in rounds.values()
		for task in tasks
		if task.round_status == "Open"
	})


def _renamed_edit_labels(snapshot, current, _evidence):
	if not (
		current.get("action") == "Edit"
		and current.get("transition_uuid")
		and snapshot.get("transition_uuid") == current["transition_uuid"]
		and snapshot.get("state") in PENDING_STATES
		and snapshot.get("next_state") in EDITING_STATES
		and snapshot.get("action") in FORMER_ACTIONS
	):
		return None
	old = {field: snapshot.get(field) for field in ("state", "action", "next_state")}
	if snapshot.get("transition_semantic_hash") != transition_semantic_hash({**current, **old}):
		return None
	return {field: current[field] for field in (*old, "transition_semantic_hash")}


def _check_edit_identity(rounds, current):
	for round_id, (tasks, _retiring) in rounds.items():
		for task in tasks:
			if task.round_status != "Open":
				continue
			for row in (frappe.parse_json(task.round_manifest) or {}).get("transitions", []):
				if row.get("action") in FORMER_ACTIONS and not _renamed_edit_labels(row, current, None):
					frappe.throw(
						_("Resolve UTP approval round {0} before replacing Stop Workflow.").format(round_id)
					)


def reconcile_open_rounds():
	from dinext_common.workflow_approval.engine import _transition_dict
	from dinext_common.workflow_approval.localization import _rename_round_task

	rounds = _affected_rounds()
	_check_rounds(rounds)
	if not _open_sources(rounds):
		return
	workflow = frappe.get_doc("Workflow", WORKFLOW)
	edit = next(
		row for row in workflow.transitions
		if row.state in PENDING_STATES and row.action == "Edit" and row.next_state in EDITING_STATES
	)
	current = _transition_dict(edit)
	_check_edit_identity(rounds, current)
	rules = {"states": {}, "recover_legacy_transition": _renamed_edit_labels}
	# The migration must update the stored round without routing the source through another active Workflow.
	for tasks, _retiring in rounds.values():
		for task in tasks:
			if task.round_status == "Open":
				_rename_round_task(
					frappe.get_doc("Workflow Task", task.name, for_update=True),
					{current["transition_uuid"]: current}, {}, rules,
				)
