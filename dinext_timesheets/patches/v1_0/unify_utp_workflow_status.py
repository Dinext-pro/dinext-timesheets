"""Move the authoritative position state without replaying Workflow actions."""

from __future__ import annotations

import ast
from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import dataclass, field

import frappe
from frappe import _
from frappe.utils import cint, get_datetime

POSITION = "User Timesheet Position"
STATUS = "status"
LEGACY_STATUS = "workflow_state"
ACTIVE_ROUNDS = ("Open", "Stalled", "Conflicted", "Finalizing")
ACTIVE_PROCESSES = ("Prepared", "Running")
ACTIVATION = "custom_activation_condition"
BATCH_SIZE = 500


class MigrationBlocked(frappe.ValidationError):
	"""The stored configuration or approval evidence needs operator review."""


@dataclass
class MigrationPlan:
	workflows: dict = field(default_factory=lambda: defaultdict(dict))
	states: dict = field(default_factory=dict)
	transitions: dict = field(default_factory=dict)
	tasks: dict = field(default_factory=dict)
	task_transitions: dict = field(default_factory=dict)
	positions: dict = field(default_factory=lambda: defaultdict(list))
	retired_fields: set = field(default_factory=set)
	property_setters: list = field(default_factory=list)

	def has_changes(self):
		return any((
			self.workflows, self.states, self.transitions, self.tasks, self.task_transitions, self.positions,
			self.retired_fields, self.property_setters,
		))


def rewrite_condition(condition, previous_field, retired_fields, *, reject_existing_status=False):
	"""Replace only direct field references and retain the surrounding expression."""
	if not condition or not condition.strip() or not retired_fields:
		return condition
	expression = condition.strip()
	tree = ast.parse(expression, mode="eval")
	parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
	replacements = []
	claimed = set()
	reads_status = False
	lines = expression.encode().splitlines(keepends=True)
	offsets = [0]
	for line in lines:
		offsets.append(offsets[-1] + len(line))

	def replace(node, fieldname, value):
		nonlocal reads_status
		if fieldname == STATUS:
			reads_status = True
		if fieldname not in retired_fields:
			return
		if fieldname != previous_field:
			raise ValueError("condition reads another scheme's retired state field")
		start = offsets[node.lineno - 1] + node.col_offset
		end = offsets[node.end_lineno - 1] + node.end_col_offset
		if isinstance(node, ast.Attribute):
			start = end - len(fieldname.encode())
		replacements.append((start, end, value))
		claimed.add(node)

	for doc in (node for node in ast.walk(tree) if isinstance(node, ast.Name) and node.id == "doc"):
		reference = parents.get(doc)
		if isinstance(reference, ast.Attribute) and reference.value is doc:
			call = parents.get(reference)
			if reference.attr != "get" and not (isinstance(call, ast.Call) and call.func is reference):
				replace(reference, reference.attr, STATUS.encode())
				continue
			key = (
				call.args[0]
				if reference.attr == "get" and isinstance(call, ast.Call) and call.func is reference and call.args
				else None
			)
		elif isinstance(reference, ast.Subscript) and reference.value is doc:
			key = reference.slice
		else:
			key = None
		if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
			raise ValueError("condition accesses the document through a dynamic field or operation")
		replace(key, key.value, repr(STATUS).encode())

	if reads_status and (replacements or reject_existing_status):
		raise ValueError("condition depends on the existing status separately from the old Workflow state")

	for node in ast.walk(tree):
		if node in claimed:
			continue
		if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in retired_fields:
			raise ValueError("condition contains an indirect reference to a retired state field")
		if isinstance(node, ast.Attribute) and node.attr in retired_fields:
			raise ValueError("condition contains an indirect reference to a retired state field")

	encoded = expression.encode()
	for start, end, value in sorted(replacements, reverse=True):
		encoded = encoded[:start] + value + encoded[end:]
	return condition.replace(expression, encoded.decode(), 1) if replacements else condition


def confirm_state(position, workflow, process, tasks, valid_states):
	"""Keep source state as the authority and verify stored approval evidence."""
	round_ids = {task.approval_round_id for task in tasks}
	if any(task.round_status == "Finalizing" for task in tasks):
		raise MigrationBlocked(
			_("Finish the finalizing Workflow round for timesheet position {0} before migrating its status.")
			.format(position.name)
		)
	if len(round_ids) > 1 or (tasks and not all(round_ids)):
		raise MigrationBlocked(_("Timesheet position {0} has ambiguous active approval rounds.").format(position.name))

	if not workflow:
		raise MigrationBlocked(_("Timesheet position {0} has no confirmed Workflow.").format(position.name))
	state = position.get(workflow.workflow_state_field)
	if (process and (process.workflow != workflow.name or process.current_state != state or not state)) or any(
		task.workflow != workflow.name
		or (task.get("workflow_process") or None) != (process.name if process else None)
		or task.workflow_state != state
		or not state
		for task in tasks
	):
		raise MigrationBlocked(
			_("The stored Workflow state and active approval evidence disagree for timesheet position {0}.")
			.format(position.name)
		)
	state = state or position.get(STATUS)
	if state and (
		state not in valid_states
		or not any(
			row.state == state and cint(row.doc_status) == cint(position.docstatus)
			for row in workflow.states
		)
	):
		raise MigrationBlocked(
			_("State {0} is invalid for timesheet position {1} in Workflow {2}.")
			.format(state, position.name, workflow.name)
		)
	return state


def _plan_workflows(plan, workflows):
	projected = {}
	for name, workflow in workflows.items():
		previous_field = workflow.workflow_state_field
		if previous_field != STATUS:
			plan.workflows[name]["workflow_state_field"] = STATUS

		def rewrite(value, row_name):
			try:
				return rewrite_condition(value, previous_field, plan.retired_fields)
			except (SyntaxError, ValueError) as error:
				raise MigrationBlocked(
					_("Resolve the condition on {0} in Workflow {1} before migrating position statuses. {2}")
					.format(row_name, name, error)
				) from error

		after = workflow.as_dict()
		after.workflow_state_field = STATUS
		after[ACTIVATION] = rewrite(workflow.get(ACTIVATION), name)
		if after[ACTIVATION] != workflow.get(ACTIVATION):
			plan.workflows[name][ACTIVATION] = after[ACTIVATION]
		for row in after.transitions:
			rewritten = rewrite(row.condition, row.name)
			if row.condition != rewritten:
				row.condition = rewritten
				plan.transitions[row.name] = rewritten
		for row in after.states:
			if row.update_field not in plan.retired_fields | {STATUS}:
				continue
			if row.update_value != row.state:
				raise MigrationBlocked(
					_("Workflow {0} uses a separate position status for state {1}. Resolve the mapping before migrating.")
					.format(name, row.state)
				)
			row.update_field = row.update_value = None
			plan.states[row.name] = {"update_field": None, "update_value": None}
		projected[name] = after
	return projected


def _status_metadata(plan, workflows):
	custom_fields = {
		row.fieldname: row
		for row in frappe.get_all("Custom Field", filters={"dt": POSITION}, fields=["fieldname", "fieldtype", "options"])
	}
	columns = set(frappe.db.get_table_columns(POSITION))
	for fieldname in {workflow.workflow_state_field for workflow in workflows.values()} - {STATUS}:
		field = custom_fields.get(fieldname)
		if not field or fieldname not in columns or (field.fieldtype, field.options) != ("Link", "Workflow State"):
			raise MigrationBlocked(
				_("The old status field {0} on timesheet positions is not a dedicated Workflow State link.")
				.format(fieldname)
			)
		plan.retired_fields.add(fieldname)
	if LEGACY_STATUS in custom_fields:
		plan.retired_fields.add(LEGACY_STATUS)
	property_setters = frappe.get_all(
		"Property Setter", filters={"doc_type": POSITION}, fields=["name", "field_name", "property"],
	)
	plan.property_setters = [
		row.name for row in property_setters
		if row.field_name in plan.retired_fields or (row.field_name == STATUS and row.property in ("fieldtype", "options"))
	]


def _active_evidence(names):
	base = {"reference_doctype": POSITION, "reference_name": ("in", names)}
	contexts = {}
	processes = defaultdict(list)
	tasks = defaultdict(list)
	if frappe.db.table_exists("Workflow Document Context") and frappe.db.table_exists("Workflow Process"):
		for row in frappe.get_all(
			"Workflow Document Context", filters=base,
			fields=["reference_name", "source_created_at", "active_process", "routing_error"],
		):
			contexts[(row.reference_name, get_datetime(row.source_created_at))] = row
		for row in frappe.get_all(
			"Workflow Process", filters={**base, "status": ("in", ACTIVE_PROCESSES)},
			fields=["name", "reference_name", "source_created_at", "workflow", "status", "current_state"],
		):
			processes[(row.reference_name, get_datetime(row.source_created_at))].append(row)
	if frappe.db.table_exists("Workflow Task") and frappe.db.has_column("Workflow Task", "round_status"):
		fields = [
			"reference_name", "source_created_at", "workflow_state", "workflow", "approval_round_id", "round_status",
			"name", "status", "round_manifest", "transition_uuid", "transition_semantic_hash", "action", "next_state",
		]
		if frappe.db.has_column("Workflow Task", "workflow_process"):
			fields.append("workflow_process")
		for row in frappe.get_all("Workflow Task", filters={**base, "round_status": ("in", ACTIVE_ROUNDS)}, fields=fields):
			created = get_datetime(row.source_created_at) if row.source_created_at else None
			tasks[(row.reference_name, created)].append(row)
	return contexts, processes, tasks


def _pinned_process(source, context, processes):
	if (
		len(processes) > 1
		or ((context and context.active_process) or None) != (processes[0].name if processes else None)
		or (context and context.routing_error and not (processes and processes[0].status == "Running"))
	):
		raise MigrationBlocked(
			_("Timesheet position {0} has ambiguous Workflow process data.").format(source.name)
		)
	return processes[0] if processes else None


def _select(source, workflows):
	if not any(workflow.get(ACTIVATION) for workflow in workflows):
		return workflows[0] if workflows else None
	from dinext_common.workflow_approval.scenarios.service import _match_workflow

	return _match_workflow(source, workflows)


def _project(source, state, retired_fields):
	result = source.as_dict()
	for fieldname in retired_fields:
		result.pop(fieldname, None)
	result.status = state
	return result


def _check_round_identity(source, before, after, projected_source, plan, tasks):
	from dinext_common.workflow_approval.engine import get_content_fingerprint

	if before.workflow_state_field != STATUS and source.get(STATUS) != projected_source.status:
		conditions = [(before.name, before.get(ACTIVATION)), *(
			(row.name, row.condition) for row in before.transitions if row.state == projected_source.status
		)]
		for owner, condition in conditions:
			try:
				rewrite_condition(
					condition, before.workflow_state_field, plan.retired_fields, reject_existing_status=True,
				)
			except ValueError as error:
				raise MigrationBlocked(
					_("Review the condition on {0} for timesheet position {1} before migration. {2}")
					.format(owner, source.name, error)
				) from error

	meta = {"fields": [row for row in source.meta.fields if row.fieldname not in plan.retired_fields]}
	projected_source.meta = meta
	if get_content_fingerprint(source, before).digest != get_content_fingerprint(projected_source, after).digest:
		raise MigrationBlocked(
			_("The status migration would change the approval fingerprint for timesheet position {0}.")
			.format(source.name)
		)
	_plan_round_conditions(source, projected_source.status, before, after, plan, tasks)


def _plan_round_conditions(source, state, before, after, plan, tasks):
	"""Carry a proven condition rewrite through every copy of an active decision."""
	rewritten = [row for row in before.transitions if row.state == state and row.name in plan.transitions]
	if not rewritten:
		return
	from dinext_common.workflow_approval.engine import _transition_dict, serialize_manifest

	message = _("Verify the active Workflow transition snapshots for timesheet position {0} before migrating.")
	message = message.format(source.name)
	uuid_counts = Counter(row.custom_transition_uuid for row in before.transitions)
	after_by_name = {row.name: row for row in after.transitions}
	changes = {}
	for row in rewritten:
		uuid = row.custom_transition_uuid
		if not uuid or uuid_counts[uuid] != 1:
			raise MigrationBlocked(message)
		changes[uuid] = (_transition_dict(row), _transition_dict(after_by_name[row.name]))
	old_hashes = {old["transition_semantic_hash"] for old, _ in changes.values()}
	old_labels = {(old["state"], old["action"], old["next_state"]) for old, _ in changes.values()}

	def matching_change(row, state_field="state"):
		uuid = row.get("transition_uuid")
		digest = row.get("transition_semantic_hash")
		labels = (row.get(state_field), row.get("action"), row.get("next_state"))
		if not uuid and (digest in old_hashes or labels in old_labels):
			raise MigrationBlocked(message)
		if uuid not in changes:
			return None
		old, new = changes[uuid]
		if digest != old["transition_semantic_hash"] or labels != (old["state"], old["action"], old["next_state"]):
			raise MigrationBlocked(message)
		return old, new

	expected_uuids = None
	for task in tasks:
		try:
			manifest = deepcopy(frappe.parse_json(task.round_manifest))
			if not isinstance(manifest["transitions"], list):
				raise ValueError
		except (KeyError, TypeError, ValueError) as error:
			raise MigrationBlocked(message) from error
		updates = {}
		uuids = set()
		for row in manifest["transitions"]:
			if not isinstance(row, dict):
				raise MigrationBlocked(message)
			match = matching_change(row)
			if not match:
				continue
			old, new = match
			uuid = old["transition_uuid"]
			if uuid in uuids or ("condition" in row and row["condition"] != old["condition"]):
				raise MigrationBlocked(message)
			uuids.add(uuid)
			row["transition_semantic_hash"] = new["transition_semantic_hash"]
			if "condition" in row:
				row["condition"] = new["condition"]
		if expected_uuids is not None and uuids != expected_uuids:
			raise MigrationBlocked(message)
		expected_uuids = uuids
		if uuids:
			updates["round_manifest"] = serialize_manifest(manifest)
		if task.status == "Completed" and (match := matching_change(task, "workflow_state")):
			if task.transition_uuid not in uuids:
				raise MigrationBlocked(message)
			updates["transition_semantic_hash"] = match[1]["transition_semantic_hash"]
		if updates:
			plan.tasks[task.name] = updates

	for row in frappe.get_all(
		"Available Workflow Transitions",
		filters={"parenttype": "Workflow Task", "parent": ("in", [task.name for task in tasks])},
		fields=["name", "state", "action", "next_state", "transition_uuid", "transition_semantic_hash"],
	):
		if match := matching_change(row):
			if row.transition_uuid not in expected_uuids:
				raise MigrationBlocked(message)
			plan.task_transitions[row.name] = {"transition_semantic_hash": match[1]["transition_semantic_hash"]}


def _plan_positions(plan, workflows, projected, valid_states):
	from dinext_common.workflow_approval.scenarios.read import load_documents

	order = lambda workflow: (cint(workflow.get("custom_selection_order")), workflow.name)
	active = sorted((workflow for workflow in workflows.values() if workflow.is_active), key=order)
	projected_active = [projected[workflow.name] for workflow in active]
	after_name = ""
	while names := frappe.get_all(
		POSITION, filters={"name": (">", after_name)}, pluck="name", limit=BATCH_SIZE, order_by="name asc",
	):
		after_name = names[-1]
		contexts, processes, tasks = _active_evidence(names)
		for source in load_documents(POSITION, names).values():
			key = (source.name, get_datetime(source.creation))
			unknown_rounds = tasks.get((source.name, None), [])
			if unknown_rounds:
				raise MigrationBlocked(
					_("An active Workflow round has no source timestamp for timesheet position {0}.")
					.format(source.name)
				)
			round_tasks = tasks.get(key, [])
			process = _pinned_process(source, contexts.get(key), processes.get(key, []))
			if process:
				workflow = workflows.get(process.workflow)
			elif round_tasks:
				workflow = workflows.get(round_tasks[0].workflow)
			else:
				workflow = _select(source, active)

			if workflow or process or round_tasks:
				state = confirm_state(source, workflow, process, round_tasks, valid_states)
			else:
				candidates = {source.get(fieldname) for fieldname in plan.retired_fields | {STATUS}} - {None, ""}
				if len(candidates) > 1 or candidates - valid_states:
					raise MigrationBlocked(
						_("Timesheet position {0} has ambiguous status data without a selected Workflow.").format(source.name)
					)
				state = next(iter(candidates), source.status)
			projected_source = _project(source, state, plan.retired_fields)
			if round_tasks:
				_check_round_identity(source, workflow, projected[workflow.name], projected_source, plan, round_tasks)
			if not process and not round_tasks:
				next_workflow = _select(projected_source, projected_active)
				if (workflow.name if workflow else None) != (next_workflow.name if next_workflow else None):
					raise MigrationBlocked(
						_("The status migration would change Workflow selection for timesheet position {0}.").format(source.name)
					)
			if state != source.status:
				plan.positions[state].append(source.name)


def preflight():
	"""Prepare and prove every write before moving any position state."""
	plan = MigrationPlan()
	if not frappe.db.table_exists(POSITION):
		return plan
	workflows = {
		name: frappe.get_doc("Workflow", name)
		for name in frappe.get_all("Workflow", filters={"document_type": POSITION}, pluck="name", order_by="name asc")
	}
	_status_metadata(plan, workflows)
	projected = _plan_workflows(plan, workflows)
	if plan.has_changes():
		if frappe.db.table_exists("Submission Queue") and frappe.db.exists(
			"Submission Queue", {"ref_doctype": POSITION, "status": "Queued"},
		):
			raise MigrationBlocked(_("Finish queued timesheet position submissions before migrating their statuses."))
		_plan_positions(plan, workflows, projected, set(frappe.get_all("Workflow State", pluck="name")))
	return plan


def migrate():
	"""Apply a proved migration within the caller's maintenance transaction."""
	plan = preflight()
	if not plan.has_changes():
		return {"positions": 0, "workflows": 0}
	field = next((row for row in frappe.get_doc("DocType", POSITION).fields if row.fieldname == STATUS), None)
	if not field or (field.fieldtype, field.options) != ("Link", "Workflow State"):
		raise MigrationBlocked(_("Load the updated User Timesheet Position DocType before migrating statuses."))
	for status, names in plan.positions.items():
		for start in range(0, len(names), BATCH_SIZE):
			frappe.db.set_value(
				POSITION, {"name": ("in", names[start : start + BATCH_SIZE])}, STATUS, status,
				update_modified=False,
			)
	for doctype, changes in (
		("Workflow", plan.workflows),
		("Workflow Document State", plan.states),
		("Workflow Transition", {name: {"condition": value} for name, value in plan.transitions.items()}),
		("Workflow Task", plan.tasks),
		("Available Workflow Transitions", plan.task_transitions),
	):
		for name, values in changes.items():
			frappe.db.set_value(doctype, name, values, update_modified=False)
	if plan.property_setters:
		frappe.db.delete("Property Setter", {"name": ("in", plan.property_setters)})
	if plan.retired_fields:
		frappe.db.delete("Custom Field", {"dt": POSITION, "fieldname": ("in", sorted(plan.retired_fields))})
	frappe.clear_cache(doctype=POSITION)
	frappe.clear_cache(doctype="Workflow")
	for name in plan.workflows:
		frappe.clear_document_cache("Workflow", name)
	return {"positions": sum(map(len, plan.positions.values())), "workflows": len(plan.workflows)}


def guard_parallel_migration():
	"""Leave legacy sites unchanged until the explicit Common cutover."""
	if not frappe.conf.get("enable_parallel_workflow_approval"):
		return
	plan = preflight()
	if plan.has_changes():
		try:
			from dinext_common.workflow_approval.migration import assert_cutover_compatibility
		except ImportError as error:
			raise MigrationBlocked(_("Update Dinext Common before migrating timesheet position statuses.")) from error

		assert_cutover_compatibility()


def execute():
	if frappe.conf.get("enable_parallel_workflow_approval"):
		return migrate()
