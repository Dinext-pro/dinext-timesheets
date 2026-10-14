"""Store timesheet and position statuses in English and seed Timesheet Settings."""

from __future__ import annotations

import json

import frappe

from dinext_timesheets.timesheet_status import (
	UT_STATUS_FROM_RUSSIAN,
	UTP_STATUS_FROM_RUSSIAN,
)


def execute() -> None:
	_ensure_workflow_state("Editing")
	_ensure_workflow_state("Pending Approval")
	_ensure_workflow_state("Approved")
	_ensure_workflow_state("Rejected")
	_rewrite_utp_workflow()
	_rewrite_column("User Timesheet", "ut_status", UT_STATUS_FROM_RUSSIAN)
	_rewrite_column("User Timesheet Position", "status", UTP_STATUS_FROM_RUSSIAN)
	_rewrite_column("User Timesheet Position", "workflow_state", UTP_STATUS_FROM_RUSSIAN)
	_rewrite_tasks()
	_rewrite_task_manifests()
	from dinext_timesheets.timesheet_settings import seed_default_rules

	seed_default_rules()


def _ensure_workflow_state(name: str) -> None:
	if frappe.db.exists("Workflow State", name):
		return
	doc = frappe.new_doc("Workflow State")
	doc.workflow_state_name = name
	doc.insert(ignore_permissions=True)


def _rewrite_utp_workflow() -> None:
	if not frappe.db.exists("Workflow", "UTP Workflow"):
		return
	for doctype, fields in (
		("Workflow Document State", ("state", "update_value")),
		("Workflow Transition", ("state", "next_state")),
	):
		for field in fields:
			_rewrite_column(
				doctype,
				field,
				UTP_STATUS_FROM_RUSSIAN,
				{"parent": "UTP Workflow", "parenttype": "Workflow"},
			)


def _rewrite_tasks() -> None:
	filters = {"reference_doctype": "User Timesheet Position"}
	for field in ("workflow_state", "state", "next_state"):
		if frappe.db.has_column("Workflow Task", field):
			_rewrite_column("Workflow Task", field, UTP_STATUS_FROM_RUSSIAN, filters)


def _rewrite_task_manifests() -> None:
	if not frappe.db.has_column("Workflow Task", "round_manifest"):
		return
	hashes = _current_utp_transition_hashes()
	names = frappe.get_all(
		"Workflow Task",
		filters={
			"reference_doctype": "User Timesheet Position",
			"round_manifest": ("is", "set"),
		},
		pluck="name",
	)
	for name in names:
		raw = frappe.db.get_value("Workflow Task", name, "round_manifest")
		manifest = _load_manifest(raw)
		if _translate_manifest(manifest, hashes):
			frappe.db.set_value(
				"Workflow Task",
				name,
				"round_manifest",
				json.dumps(manifest, ensure_ascii=False, separators=(",", ":")),
				update_modified=False,
			)


def _current_utp_transition_hashes() -> dict[str, str]:
	from dinext_common.workflow_approval.policy import transition_semantic_hash

	if not frappe.db.exists("Workflow", "UTP Workflow"):
		return {}
	rows = frappe.get_all(
		"Workflow Transition",
		filters={"parent": "UTP Workflow", "parenttype": "Workflow"},
		fields=[
			"custom_transition_uuid",
			"action",
			"allow_self_approval",
			"allowed",
			"condition",
			"custom_minimum_approvals",
			"custom_parallel_approval_policy",
			"next_state",
			"state",
		],
	)
	return {
		str(row.custom_transition_uuid or ""): transition_semantic_hash(
			{
				"action": row.action or "",
				"allow_self_approval": row.allow_self_approval or 0,
				"allowed": row.allowed or "",
				"condition": row.condition or "",
				"minimum_approvals": row.custom_minimum_approvals,
				"next_state": row.next_state or "",
				"policy": row.custom_parallel_approval_policy,
				"state": row.state or "",
			}
		)
		for row in rows
	}


def _load_manifest(raw: object) -> dict:
	if isinstance(raw, dict):
		return raw
	try:
		loaded = json.loads(raw or "{}")
	except (TypeError, json.JSONDecodeError):
		return {}
	return loaded if isinstance(loaded, dict) else {}


def _translate_manifest(manifest: dict, hashes: dict[str, str]) -> bool:
	from dinext_common.workflow_approval.policy import transition_semantic_hash

	changed = False
	for row in manifest.get("transitions") or []:
		if not isinstance(row, dict):
			continue
		for field in ("state", "next_state"):
			current = row.get(field) or ""
			translated = UTP_STATUS_FROM_RUSSIAN.get(current, current)
			if translated != current:
				row[field] = translated
				changed = True
		uuid = str(row.get("transition_uuid") or "")
		if uuid in hashes:
			updated = hashes[uuid]
		else:
			updated = transition_semantic_hash(row)
		if row.get("transition_semantic_hash") != updated:
			row["transition_semantic_hash"] = updated
			changed = True
	return changed


def _rewrite_column(
	doctype: str,
	field: str,
	mapping: dict[str, str],
	filters: dict | None = None,
) -> None:
	if not frappe.db.has_column(doctype, field):
		return
	for old, new in mapping.items():
		if old == new:
			continue
		names = frappe.get_all(
			doctype,
			filters={field: old, **(filters or {})},
			pluck="name",
		)
		for name in names:
			frappe.db.set_value(doctype, name, field, new, update_modified=False)
