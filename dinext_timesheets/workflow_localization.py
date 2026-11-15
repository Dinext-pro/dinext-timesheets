# ruff: noqa: RUF001
"""Preserve Timesheet decisions across workflow label changes."""

from collections import defaultdict

from dinext_common.workflow_approval.localization import (
	_labels,
	_same_named_transition,
	renamed_transition,
)
from dinext_common.workflow_approval.policy import required_approvals

_STATE_NAMES = {
	"Редактирование": "Editing",
	"На согласовании": "Pending Approval",
	"Согласовано": "Approved",
	"Отклонено": "Rejected",
}
_UTP_LEGACY_VOTES = {"Approve": "Согласовано", "Reject": "Не согласовано"}


def label_rules() -> dict:
	return {
		"states": _STATE_NAMES,
		"collect_legacy_evidence": collect_legacy_evidence,
		"recover_legacy_transition": recover_legacy_transition,
	}


def collect_legacy_evidence(tasks, current):
	"""Collect the original hashes preserved in personal rows by the earlier UTP migration."""
	first = tasks[0]
	evidence = defaultdict(dict)
	if first.workflow != "UTP Workflow" or any(task.round_manifest != first.round_manifest for task in tasks):
		return evidence
	if len({task.approver for task in tasks}) != len(tasks):
		return evidence
	for task in tasks:
		for child in task.available_workflow_transitions:
			uuid = child.transition_uuid
			config = current.get(uuid, {})
			old_action = _UTP_LEGACY_VOTES.get(config.get("action"))
			option = child.as_dict()
			if not old_action or not _same_named_transition(task.workflow, option, config):
				continue
			# The earlier migration changed displayed labels and the manifest hash separately.
			# The personal row can still prove the original hash using the exact old action.
			old_option = {**option, "action": old_action}
			if not renamed_transition(task.workflow, old_option, config):
				continue
			if task.status == "Completed" and task.transition_uuid == uuid:
				if task.transition_semantic_hash != child.transition_semantic_hash or _labels(
					task.workflow, task
				) != _labels(task.workflow, option):
					continue
			evidence[uuid][task.approver] = child
	for task in tasks:
		if task.status == "Completed" and task.approver not in evidence.get(task.transition_uuid, {}):
			evidence.pop(task.transition_uuid, None)
	return evidence


def recover_legacy_transition(row, current, evidence):
	"""Repair a stale manifest only when every actor's personal row proves the current rule."""
	legacy_action = _UTP_LEGACY_VOTES.get(current.get("action"))
	if (
		not legacy_action
		or row.get("action") != legacy_action
		or row.get("state") != current["state"]
		or row.get("next_state") != current["next_state"]
	):
		return None
	if not _same_named_transition("UTP Workflow", row, current):
		return None
	if row.get("allowed") != current["allowed"] or row.get("policy") != current["policy"]:
		return None
	approvers = set(row.get("eligible_approvers") or [])
	if not approvers or approvers != set(evidence):
		return None
	threshold = required_approvals(current["policy"], current["minimum_approvals"], len(approvers))
	if row.get("threshold") != threshold or any(child.threshold != threshold for child in evidence.values()):
		return None
	return {**_labels("UTP Workflow", row), "transition_semantic_hash": current["transition_semantic_hash"]}
