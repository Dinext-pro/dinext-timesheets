"""UTP ↔ Workflow Task bridge (ISS-2026-00926 phase 2 block B).

Ports demodev Server Scripts:
- UTP Check WT Before Save V2
- UTP Proccess WT After Save
- UTP_Deleted_WTs_Deleted

Calls existing API Server Scripts ``Workflow_Task_Processing`` /
``Workflow_Task_Processing_After_Save`` (shared with AFL etc.).
"""

from __future__ import annotations

import frappe
from frappe.utils.safe_exec import call_whitelisted_function


def sync_status_from_workflow_state(doc) -> None:
	doc.status = doc.workflow_state


def process_workflow_tasks_before_save(doc) -> None:
	"""Before Save: sync status, run Workflow_Task_Processing API SS."""
	sync_status_from_workflow_state(doc)
	# SS sandbox ``frappe.call`` → call_whitelisted_function (not frappe.call attr path)
	result = call_whitelisted_function("Workflow_Task_Processing", doc=doc)
	if not result:
		return

	new_doc = getattr(result, "doc", None) or (
		result.get("doc") if isinstance(result, dict) else None
	)
	if not new_doc:
		return

	# SS reassigns ``doc``; in hooks we must mutate the in-save document.
	if hasattr(new_doc, "as_dict"):
		_apply_doc_updates(doc, new_doc)
	elif isinstance(new_doc, dict):
		for key, value in new_doc.items():
			if key.startswith("_") or key in ("doctype", "name"):
				continue
			if key == "table":
				continue
			doc.set(key, value)

	doc.status = doc.workflow_state


def process_workflow_tasks_after_save(doc) -> None:
	call_whitelisted_function("Workflow_Task_Processing_After_Save", doc=doc)


def delete_linked_workflow_tasks(doc) -> None:
	workflow_tasks = frappe.get_all(
		"Workflow Task",
		filters={"wt_docname": doc.name},
		ignore_permissions=True,
	)
	for task in workflow_tasks:
		task_doc = frappe.get_doc("Workflow Task", task.name)
		task_doc.delete(ignore_permissions=True)


def _apply_doc_updates(target, source) -> None:
	"""Copy scalar fields from processing result onto the document being saved."""
	skip = {"name", "doctype", "owner", "creation", "modified", "modified_by", "idx"}
	for key, value in source.as_dict().items():
		if key in skip or key.startswith("_"):
			continue
		# Keep child tables from the in-save doc unless empty on target.
		meta = target.meta.get_field(key)
		if meta and meta.fieldtype in ("Table", "Table MultiSelect"):
			continue
		target.set(key, value)
