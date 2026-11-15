"""Scenario-specific actions and rollup for timesheet positions."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from contextlib import contextmanager
from copy import deepcopy
from typing import Literal, NotRequired, TypedDict

import frappe
from frappe import _
from frappe.utils import cint

from dinext_common.workflow_approval import engine, request_receipts
from dinext_common.workflow_approval.scenarios import service

POSITION = "User Timesheet Position"
_NO_ELIGIBLE_APPROVERS = getattr(engine, "NoEligibleApproversError", None)
_MISSING_APPROVER_ERRORS = (_NO_ELIGIBLE_APPROVERS,) if _NO_ELIGIBLE_APPROVERS else ()


class TimesheetTransitionError(getattr(engine, "WorkflowDomainRollbackError", frappe.ValidationError)):
	"""Roll back the operation that would leave the timesheet in an invalid state."""


@contextmanager
def atomic_timesheet_transition(also_rollback: tuple[type[Exception], ...] = ()):
	"""Restore pending side effects when a timesheet transition rolls back."""
	savepoint = f"timesheet_transition_{frappe.generate_hash(length=12)}"
	cascade = deepcopy(getattr(frappe.local, "workflow_scenario_cascade", None))
	managers = (frappe.db.before_commit, frappe.db.after_commit,
		frappe.db.before_rollback, frappe.db.after_rollback)
	callbacks = [(manager, tuple(manager._functions)) for manager in managers]
	realtime_log = getattr(frappe.local, "_realtime_log", None)
	realtime_count = len(realtime_log or [])
	frappe.db.savepoint(savepoint)
	try:
		yield
	except (TimesheetTransitionError, *also_rollback):
		frappe.db.rollback(save_point=savepoint)
		for manager, previous in callbacks:
			manager.reset()
			for callback in previous:
				manager.add(callback)
		frappe.local.workflow_scenario_cascade = cascade
		if realtime_log is not None:
			del realtime_log[realtime_count:]
			frappe.local._realtime_log = realtime_log
		elif hasattr(frappe.local, "_realtime_log"):
			del frappe.local._realtime_log
		raise
	finally:
		frappe.db.release_savepoint(savepoint)


class TimesheetPositionOption(TypedDict):
	action: str
	next_state: str
	comment_is_required: bool
	mode: Literal["vote", "domain"]
	task: str | None
	workflow: str
	process_id: str | None
	transition_uuid: str | None
	round_id: NotRequired[str]
	threshold: NotRequired[int]


class TimesheetPositionCommand(TypedDict):
	name: str
	mode: Literal["vote", "domain"]
	task: str | None
	next_state: str
	workflow: str
	process_id: str | None
	transition_uuid: str | None


class TimesheetPositionTarget(TypedDict):
	name: str
	workflow: str
	process_id: str | None
	task_name: str | None
	transition_uuid: str | None
	next_state: str


class TimesheetPositionAction(TypedDict):
	action: str
	comment_is_required: bool
	confirm_return_to_editing: bool
	positions: list[TimesheetPositionCommand]
	targets: list[TimesheetPositionTarget]
	runs_timesheet_checks: NotRequired[bool]


class TimesheetActionsResponse(TypedDict):
	actions: list[TimesheetPositionAction]


class TimesheetDomainResult(TypedDict):
	name: str
	transitioned: bool


class TimesheetPositionFailure(TypedDict):
	name: str | None
	error: str
	error_type: str
	workflow_error: engine.WorkflowRoundError | None


class _MandatoryCascadeError(TimesheetTransitionError):
	def __init__(self, failure: TimesheetPositionFailure):
		super().__init__(failure["error"])
		self.failure = failure


def _position_failure(
	name: str | None, cause: engine.NoEligibleApproversError, message: str | None = None,
) -> TimesheetPositionFailure:
	return {
		"name": name,
		"error": message if message is not None else str(cause),
		"error_type": type(cause).__name__,
		"workflow_error": cause.details if name else None,
	}


def _cascade_failure(position, cause: Exception) -> TimesheetPositionFailure:
	can_read = position.has_permission("read")
	name = position.name if can_read else None
	missing_approvers = isinstance(cause, _MISSING_APPROVER_ERRORS)
	if missing_approvers and can_read:
		return _position_failure(name, cause, _(
			"The timesheet status and position transitions were rolled back. "
			"Could not update related position {0}. {1}"
		).format(name, cause))
	if missing_approvers:
		return _position_failure(None, cause, _(
			"The timesheet status and position transitions were rolled back. "
			"A related position could not open its next approval round."
		))
	return {
		"name": name,
		"error": _("The timesheet status and position transitions were rolled back. "
			"A related position could not be updated."),
		"error_type": "TimesheetTransitionError",
		"workflow_error": None,
	}


class TimesheetActionResponse(TypedDict):
	timesheet: str
	results: list[engine.VoteResult | TimesheetDomainResult]
	messages: list[str]
	processed: int
	total: int
	failed: NotRequired[list[TimesheetPositionFailure]]


def _producer():
	from dinext_timesheets import workflow_approval

	return workflow_approval


def is_active() -> bool:
	from dinext_common.workflow_approval.lifecycle import is_engine_enabled

	return uses_local_scenarios() and is_engine_enabled() and service.is_ready()


def uses_local_scenarios() -> bool:
	# Older Common releases still install their own Timesheets compatibility wrappers.
	return hasattr(engine, "domain_handler") and service.is_ready()


def _request_cache_key(parent, request_id: str) -> str:
	identity = [getattr(frappe.local, "site", None), frappe.session.user, parent.name,
		str(parent.creation), request_id]
	return "timesheet_workflow_request:" + hashlib.sha256(json.dumps(identity).encode()).hexdigest()


def _replay_legacy_parent_action(parent, action: str, request_id: str, targets=None) -> TimesheetActionResponse | None:
	key = _request_cache_key(parent, request_id)
	cached = frappe.cache.get_value(key)
	if cached:
		if cached["action"] != action:
			raise engine.WorkflowApprovalConflictError(_("The action is not available for the timesheet positions"))
		if targets is not None:
			validate_targets(cached["targets"], targets)
		for target in cached["targets"]:
			frappe.get_doc(POSITION, target["name"]).check_permission("read")
		return cached["response"]
	names = frappe.get_all(POSITION, filters={"user_timesheet": parent.name}, pluck="name")
	if not names:
		return None
	prefix = request_id + ":"
	rows = frappe.get_all("Workflow Task", filters={"reference_doctype": POSITION,
		"reference_name": ("in", names), "approver": frappe.session.user, "status": ("in", ["Working", "Completed", "Cancelled"]),
		"correlation_id": ("like", prefix + "%")}, fields=["name", "reference_name", "workflow",
		"workflow_process", "transition_uuid", "action", "correlation_id", "source_created_at",
		"request_receipt_recorded", "status"], order_by="name asc")
	rows = [row for row in rows if str(row.correlation_id or "").startswith(prefix)
		and (row.get("status", "Completed") == "Completed" or row.get("request_receipt_recorded"))]
	if not rows:
		return None
	if any(row.get("request_receipt_recorded") for row in rows):
		raise engine.WorkflowApprovalConflictError(_("The Workflow request has expired. Refresh the document before acting."))
	from frappe.utils import get_datetime

	valid = []
	for row in rows:
		source = frappe.get_doc(POSITION, row.reference_name)
		source.check_permission("read")
		if row.source_created_at and get_datetime(row.source_created_at) != get_datetime(source.creation):
			continue
		if row.action != action:
			raise engine.WorkflowApprovalConflictError(_("The action is not available for the timesheet positions"))
		valid.append(row)
	if not valid:
		return None
	valid.sort(key=lambda row: (str(row.correlation_id).removeprefix(prefix).zfill(6), row.name))
	expected = [{"name": row.reference_name, "workflow": row.workflow, "process_id": row.workflow_process,
		"task_name": row.name, "transition_uuid": row.transition_uuid} for row in valid]
	if targets is not None:
		validate_targets(expected, targets)
	results = [engine.cast_vote(row.name, action=action, transition_uuid=row.transition_uuid,
		request_id=row.correlation_id, completion_source="Bulk") for row in valid]
	return {"timesheet": parent.name, "results": results, "messages": [], "processed": len(valid), "total": len(valid)}


def _request_parameters(parent, action, comment, targets):
	if isinstance(targets, str):
		try:
			targets = json.loads(targets)
		except ValueError:
			raise engine.WorkflowApprovalConflictError(
				_("No unique active Workflow Task is available for this action")
			) from None
	return [request_receipts.target(parent), action, engine.normalize_comment(comment, required=False), targets]


def group_position_actions(
	current: dict[str, str], options: dict[str, list[TimesheetPositionOption]],
) -> list[TimesheetPositionAction]:
	"""Keep each eligible position's identity and omit action names ambiguous on any position."""
	ambiguous = {action for items in options.values()
		for action, count in Counter(item["action"] for item in items).items() if count > 1}
	grouped: dict[str, TimesheetPositionAction] = {}
	for name, items in options.items():
		for item in items:
			action = item["action"]
			if action in ambiguous:
				continue
			row = grouped.setdefault(action, {"action": action, "comment_is_required": False,
				"confirm_return_to_editing": False, "positions": [], "targets": []})
			row["comment_is_required"] |= bool(item.get("comment_is_required"))
			row["confirm_return_to_editing"] |= current.get(name) == "Approved" and item["next_state"] == "Editing"
			position: TimesheetPositionCommand = {
				"name": name,
				"mode": item["mode"],
				"task": item["task"],
				"next_state": item["next_state"],
				"workflow": item["workflow"],
				"process_id": item["process_id"],
				"transition_uuid": item["transition_uuid"],
			}
			row["positions"].append(position)
			row["targets"].append({
				"name": name,
				"workflow": position["workflow"],
				"process_id": position["process_id"],
				"task_name": position["task"],
				"transition_uuid": position["transition_uuid"],
				"next_state": position["next_state"],
			})
	return sorted(grouped.values(), key=lambda row: row["action"])


def validate_targets(expected: list[TimesheetPositionTarget], targets: object) -> None:
	"""Reject an old menu rather than rediscovering an action in a replacement process."""
	try:
		targets = json.loads(targets) if isinstance(targets, str) else targets
	except (ValueError, TypeError):
		targets = None
	fields = ("workflow", "process_id", "task_name", "transition_uuid")
	if not isinstance(targets, list) or any(not isinstance(row, dict) or
		not isinstance(row.get("name"), str) or not row["name"] for row in targets):
		raise engine.WorkflowApprovalConflictError(_("No unique active Workflow Task is available for this action"))
	by_name = {row.get("name"): row for row in targets}
	if len(by_name) != len(targets) or set(by_name) != {row["name"] for row in expected}:
		raise engine.WorkflowApprovalConflictError(_("No unique active Workflow Task is available for this action"))
	for row in expected:
		candidate = by_name[row["name"]]
		if any(field not in candidate or candidate[field] != row.get(field) for field in fields):
			raise engine.WorkflowApprovalConflictError(_("No unique active Workflow Task is available for this action"))


def _filling_check_rule() -> dict | None:
	from dinext_timesheets.timesheet_settings import position_rules

	return next((row for row in position_rules() if row["check_timesheet"]), None)


def _rollup_settings():
	from dinext_timesheets.timesheet_settings import matching_position_rule

	return matching_position_rule, _filling_check_rule


def _position_state(position, context: service.WorkflowContext) -> str:
	return str((context["state"] if context["workflow"] else position.get("status")) or "")


def _move_position(position, context: service.WorkflowContext, target: str, reason: str) -> bool:
	if _position_state(position, context) == target:
		return False
	field = context["state_field"]
	if not field:
		raise engine.WorkflowApprovalConflictError(_("The source document has no active Workflow"))
	reached = engine.apply_domain_transition(
		POSITION, position.name, target, reason=reason, actor=frappe.session.user,
	)
	# The engine returns the document at the transition, before reconciling a new process.
	if reached.get(field) != target:
		raise engine.WorkflowApprovalConflictError(_("The source workflow state has changed"))
	return True


def _locked_positions(timesheet_name: str, source) -> list:
	names = frappe.db.get_values(
		POSITION, {"user_timesheet": timesheet_name}, "name", order_by="name asc",
		pluck=True, for_update=True,
	)
	return [
		source if name == source.name else frappe.get_doc(POSITION, name, for_update=True)
		for name in names
	]


def _validate_filling(parent, positions) -> None:
	try:
		_producer()._validate_positions(parent, positions)
	except frappe.ValidationError as cause:
		error = TimesheetTransitionError(str(cause))
		if message_id := getattr(cause, "__frappe_exc_id", None):
			setattr(error, "__frappe_exc_id", message_id)
		raise error from cause


def validate_position_vote(source, next_state: str) -> None:
	"""Validate the saved timesheet for a new vote into the checked position status."""
	if not source.user_timesheet:
		return
	rule = _filling_check_rule()
	if not rule or rule["position_status"] != next_state:
		return
	parent = frappe.get_doc("User Timesheet", source.user_timesheet, for_update=True)
	_validate_filling(parent, _locked_positions(parent.name, source))


def recalculate_parent(parent, changed_position, old_status: str | None) -> None:
	"""Apply the winning Position Rules row to the locked aggregate."""
	matching_position_rule, get_check_rule = _rollup_settings()
	positions = _locked_positions(parent.name, changed_position)
	contexts = [service.get_context(position) for position in positions]
	counts = Counter(_position_state(position, context) for position, context in zip(positions, contexts, strict=True))
	rule = matching_position_rule(counts)
	if not rule or parent.ut_status == rule["timesheet_status"]:
		return
	new_status = rule["timesheet_status"]
	check_rule = get_check_rule()
	if check_rule and new_status == check_rule["timesheet_status"]:
		_validate_filling(parent, positions)

	parent.ut_status = new_status
	parent.ut_approval_date = frappe.utils.nowdate() if new_status == "Approved" else None
	if not rule["move_all_positions"]:
		parent.save(ignore_permissions=True)
		return
	target = rule["position_status"]
	previous = getattr(frappe.flags, "in_timesheet_approval_cascade", False)
	frappe.flags.in_timesheet_approval_cascade = True
	try:
		with atomic_timesheet_transition():
			parent.save(ignore_permissions=True)
			for position, context in zip(positions, contexts, strict=True):
				if _position_state(position, context) == target:
					continue
				messages = frappe.local.message_log
				message_count = len(messages or [])
				try:
					_move_position(position, context, target, _("Timesheet status {0}").format(new_status))
				except Exception as cause:
					del (frappe.local.message_log or [])[message_count:]
					failure = _cascade_failure(position, cause)
					raise _MandatoryCascadeError(failure) from (cause if failure["name"] else None)
	finally:
		frappe.flags.in_timesheet_approval_cascade = previous


def _position_action_items(doc, context: service.WorkflowContext | None = None) -> list[TimesheetPositionOption]:
	from dinext_common.workflow_approval.scenarios.compat import document_scope

	context = context or service.get_context(doc)
	if not context["workflow"]:
		return []
	identity = {"workflow": context["workflow"], "process_id": context["process_id"]}
	filters = {"reference_doctype": POSITION, "reference_name": doc.name,
		"approver": frappe.session.user, "status": "Working", "round_status": "Open",
		"workflow": context["workflow"]}
	if context["process_id"]:
		filters["workflow_process"] = context["process_id"]
	names = frappe.get_all("Workflow Task", filters=filters, pluck="name", limit=2)
	if len(names) > 1:
		return []
	if names:
		task = frappe.get_doc("Workflow Task", names[0])
		task.check_permission("read")
		return [{"action": row.action, "next_state": row.next_state,
			"comment_is_required": bool(row.comment_is_required), "mode": "vote", "task": task.name,
			"transition_uuid": row.transition_uuid, "round_id": task.approval_round_id,
			"threshold": cint(row.threshold), **identity}
			for row in task.available_workflow_transitions if row.action and row.next_state and row.transition_uuid]
	if context["process_id"]:
		# A completed personal vote must keep waiting for the remaining quorum.
		return []
	from frappe.model.workflow import get_transitions

	with document_scope(doc):
		try:
			transitions = get_transitions(doc)
		except (frappe.ValidationError, frappe.PermissionError):
			return []
	return [{"action": row.action, "next_state": row.next_state,
		"comment_is_required": bool(row.get("custom_comment_is_required")), "mode": "domain", "task": None,
		"transition_uuid": row.get("custom_transition_uuid"), **identity}
		for row in transitions if row.get("allow_self_approval") and row.action and row.next_state]


def _mark_checks(
	actions: list[TimesheetPositionAction],
	current: dict[str, str],
	options: dict[str, list[TimesheetPositionOption]],
	current_status: str,
) -> None:
	matching_position_rule, get_check_rule = _rollup_settings()
	check_rule = get_check_rule()
	for action in actions:
		action["runs_timesheet_checks"] = bool(check_rule) and any(
			position["mode"] == "vote" and position["next_state"] == check_rule["position_status"]
			for position in action["positions"]
		)
	remaining_actions = [action for action in actions if not action["runs_timesheet_checks"]]
	if not check_rule or not remaining_actions or current_status == check_rule["timesheet_status"]:
		return

	round_ids = {
		option["round_id"]
		for position_options in options.values()
		for option in position_options
		if option.get("round_id")
	}
	votes = Counter()
	if round_ids:
		votes.update(
			(row.approval_round_id, row.transition_uuid)
			for row in frappe.get_all(
				"Workflow Task", filters={"approval_round_id": ("in", list(round_ids)), "status": "Completed"},
				fields=["approval_round_id", "transition_uuid"],
			)
		)
	reached = {
		(name, option["action"], option["transition_uuid"])
		for name, position_options in options.items()
		for option in position_options
		if option["mode"] == "domain"
		or votes[option.get("round_id"), option["transition_uuid"]] + 1 >= option.get("threshold", 1)
	}
	for action in remaining_actions:
		updates = {
			position["name"]: position["next_state"]
			for position in action["positions"]
			if (position["name"], action["action"], position["transition_uuid"]) in reached
		}
		rule = matching_position_rule(Counter(updates.get(name, state) for name, state in current.items()))
		action["runs_timesheet_checks"] = bool(
			updates and rule and rule["timesheet_status"] == check_rule["timesheet_status"]
		)


def get_timesheet_position_actions(timesheet_name: str) -> TimesheetActionsResponse:
	"""Describe actionable child positions while retaining each selected process identity."""
	parent = frappe.get_doc("User Timesheet", timesheet_name)
	parent.check_permission("read")
	current: dict[str, str] = {}
	options: dict[str, list[TimesheetPositionOption]] = {}
	for name in frappe.get_all(POSITION, filters={"user_timesheet": parent.name}, pluck="name", order_by="name asc"):
		doc = frappe.get_doc(POSITION, name)
		try:
			doc.check_permission("read")
		except frappe.PermissionError:
			# Hidden positions still count toward All without disclosing their state.
			current[name] = ""
			continue
		context = service.get_context(doc)
		current[name] = _position_state(doc, context)
		options[name] = _position_action_items(doc, context)
	actions = group_position_actions(current, options)
	_mark_checks(actions, current, options, parent.ut_status)
	return {"actions": actions}


def apply_timesheet_position_action(
	timesheet_name: str, action: str, comment: object = None, request_id: str | None = None,
	track_progress: bool = False, targets: list[TimesheetPositionTarget] | str | None = None,
) -> TimesheetActionResponse:
	"""Apply exact position decisions under the existing aggregate parent lock and rollup boundary."""
	from dinext_common.workflow_approval.api import _require_post

	_require_post()
	parent = frappe.get_doc("User Timesheet", timesheet_name, for_update=True)
	parent.check_permission("read")
	parameters = _request_parameters(parent, action, comment, targets)
	if request_id:
		key = request_receipts.request_key("Timesheet", request_id)
		receipt = request_receipts.get(key)
		replayed = request_receipts.replay(receipt, parameters) if receipt else _replay_legacy_parent_action(
			parent, action, request_id, targets
		)
		if replayed is not None:
			return replayed
	available = get_timesheet_position_actions(parent.name)
	chosen = next((row for row in available["actions"] if row["action"] == action), None)
	if not chosen:
		raise frappe.ValidationError(_("The action is not available for the timesheet positions"))
	if targets is not None:
		validate_targets(chosen["targets"], targets)
	comment = engine.normalize_comment(comment, required=chosen["comment_is_required"])
	with atomic_timesheet_transition():
		receipt = None
		if request_id:
			scopes = [request_receipts.target(parent)]
			for position in chosen["positions"]:
				source = frappe.get_doc(POSITION, position["name"], for_update=True)
				source.check_permission("read")
				scopes.append(request_receipts.target(source, position["task"]))
			receipt = request_receipts.reserve("Timesheet", request_id, parameters, scopes)
			if receipt.response is not None:
				return request_receipts.replay(receipt, parameters)
		response = _apply_position_actions(parent, chosen["positions"], action, comment, request_id, track_progress)
		if receipt:
			_include_related_receipt_targets(receipt.name, scopes, response.get("failed", []))
			request_receipts.finish(receipt.name, response)
		return response


def _include_related_receipt_targets(
	key: str, scopes: list[request_receipts.ReceiptTarget], failed: list[TimesheetPositionFailure],
) -> None:
	selected = {row["name"] for row in scopes if row["doctype"] == POSITION}
	related_names = dict.fromkeys(row["name"] for row in failed if row["name"] and row["name"] not in selected)
	if related_names:
		scopes.extend(request_receipts.target(frappe.get_doc(POSITION, name)) for name in related_names)
		frappe.db.set_value(request_receipts.DOCTYPE, key, "targets", json.dumps(scopes))


@contextmanager
def _defer_timesheet_rollup():
	previous = frappe.flags.defer_timesheet_rollup
	frappe.flags.defer_timesheet_rollup = True
	try:
		yield
	finally:
		frappe.flags.defer_timesheet_rollup = previous


def _apply_position_action(
	position: TimesheetPositionCommand, action: str, comment: str, request_id: str | None,
) -> engine.VoteResult | TimesheetDomainResult:
	source = frappe.get_doc(POSITION, position["name"], for_update=True)
	source.check_permission("read")
	live = service.get_context(source)
	if live["workflow"] != position["workflow"] or live["process_id"] != position["process_id"]:
		raise engine.WorkflowApprovalConflictError(_("The source workflow state has changed"))
	if position["mode"] == "domain":
		return {
			"name": source.name,
			"transitioned": _move_position(
				source, live, position["next_state"], _("Timesheet action {0}").format(action)
			),
		}
	if _producer()._task_no_longer_matches_source(position["task"]):
		raise engine.WorkflowApprovalConflictError(_("The source workflow state has changed"))
	return engine.cast_vote(
		position["task"], action=action, transition_uuid=position["transition_uuid"],
		comment=comment, completion_source="Bulk", request_id=request_id, receipt_managed=bool(request_id),
	)


def _apply_position_actions(
	parent, positions: list[TimesheetPositionCommand], action: str, comment: str,
	request_id: str | None, track_progress: bool,
) -> TimesheetActionResponse:
	from dinext_common.workflow_approval.api import publish_workflow_progress

	frappe.flags.timesheet_transition_messages = []
	frappe.flags.workflow_finalization_errors = []
	total = len(positions)
	report_progress = total > 1 and bool(request_id) and str(track_progress).lower() in {"1", "true"}
	results: list[engine.VoteResult | TimesheetDomainResult] = []
	failed: list[TimesheetPositionFailure] = []
	last_transition = None
	try:
		with atomic_timesheet_transition():
			with _defer_timesheet_rollup():
				for attempt, position in enumerate(positions, start=1):
					position_request_id = f"{request_id}:{attempt - 1}" if request_id else None
					message_count = len(frappe.local.message_log or [])
					try:
						with atomic_timesheet_transition(_MISSING_APPROVER_ERRORS):
							result = _apply_position_action(position, action, comment, position_request_id)
					except _MISSING_APPROVER_ERRORS as error:
						if frappe.local.message_log:
							del frappe.local.message_log[message_count:]
						failed.append(_position_failure(position["name"], error))
					except engine.WorkflowApprovalConflictError as error:
						if last_transition is None:
							raise
						_producer()._note_timesheet_transition_message(str(error))
					else:
						results.append(result)
						if result["transitioned"]:
							last_transition = position["name"]
					if report_progress:
						publish_workflow_progress(request_id, attempt, total)
			if last_transition:
				parent.reload()
				recalculate_parent(parent, frappe.get_doc(POSITION, last_transition, for_update=True), None)
	except _MandatoryCascadeError as error:
		failed.append(error.failure)
		frappe.flags.workflow_finalization_errors = []
		frappe.flags.timesheet_transition_messages = []
		results = []
	return {
		"timesheet": parent.name,
		"results": results,
		"messages": [
			*(frappe.flags.workflow_finalization_errors or []),
			*(frappe.flags.timesheet_transition_messages or []),
		],
		"processed": total,
		"total": total,
		"failed": failed,
	}


def use_authorized_domain_transition(state_field: str) -> bool:
	return state_field != "workflow_state"
