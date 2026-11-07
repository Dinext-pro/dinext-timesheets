"""Refresh open UTP approval snapshots after renaming their editing action."""

import frappe
from frappe import _

WORKFLOW = "UTP Workflow"
POSITION = "User Timesheet Position"
FORMER_ACTIONS = {"Stop Workflow", "Остановить Воркфлоу"}


def _affected_rounds():
	fields = (
		"approval_round_id", "reference_name", "round_status", "round_manifest", "status", "action",
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
			"workflow_state": ("in", ("Pending Approval", "На согласовании")),
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
	if not frappe.flags.in_fixtures or doc.name != WORKFLOW:
		return

	incoming = [
		row for row in doc.transitions
		if (row.state, row.next_state, row.action) == ("Pending Approval", "Editing", "Edit")
	]
	if len(incoming) != 1 or not frappe.db.exists("Workflow", WORKFLOW):
		return

	previous = [
		row for row in frappe.get_doc("Workflow", WORKFLOW).transitions
		if row.state in {"Pending Approval", "На согласовании"}
		and row.next_state in {"Editing", "Редактирование"}
		and row.action in FORMER_ACTIONS | {"Edit"}
	]
	if len(previous) == 1 and previous[0].custom_transition_uuid:
		incoming[0].custom_transition_uuid = previous[0].custom_transition_uuid

	from dinext_common.workflow_approval.engine import _eligible_approvers

	rounds = _affected_rounds()
	_check_rounds(rounds)
	for name in _open_sources(rounds):
		if not _eligible_approvers(frappe.get_doc(POSITION, name), incoming[0]):
			frappe.throw(_("Position {0} has no eligible actor for Edit.").format(name))


def _open_sources(rounds):
	return sorted({
		task.reference_name
		for tasks, _retiring in rounds.values()
		for task in tasks
		if task.round_status == "Open"
	})


def reconcile_open_rounds():
	from dinext_common.workflow_approval.engine import reconcile_source

	rounds = _affected_rounds()
	_check_rounds(rounds)
	for name in _open_sources(rounds):
		reconcile_source(frappe.get_doc(POSITION, name), apply_automatic=False)
