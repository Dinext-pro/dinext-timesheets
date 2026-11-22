"""Move position defaults into existing Workflows without running source hooks."""

import frappe
from dinext_common.workflow_approval.exclusions import EXCLUSIONS_FIELD, validate_exclusions
from dinext_common.workflow_approval.metadata import ensure_workflow_fingerprint_fields

DEFAULT_EXCLUSIONS = (
	"reject_reason",
	"custom_username",
	"all_hours",
	"custom_data",
	"table.utilized_hours",
)


def execute():
	ensure_workflow_fingerprint_fields()
	for name in frappe.get_all(
		"Workflow", filters={"document_type": "User Timesheet Position"}, pluck="name"
	):
		workflow = frappe.get_doc("Workflow", name)
		existing = {row.field_path for row in workflow.get(EXCLUSIONS_FIELD) or []}
		for path in DEFAULT_EXCLUSIONS:
			if path not in existing:
				workflow.append(EXCLUSIONS_FIELD, {"field_path": path})
		validate_exclusions(workflow)
		# Workflow.save() backfills blank source states. Only this child table needs persistence.
		workflow.update_child_table(EXCLUSIONS_FIELD)
		frappe.clear_document_cache("Workflow", name)
