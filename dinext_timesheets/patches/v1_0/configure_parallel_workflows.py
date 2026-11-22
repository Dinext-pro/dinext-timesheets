"""Configure timesheet workflows for the shared approval engine."""

import frappe

from dinext_timesheets.patches.v1_0.utp_team_lead_condition import migrate_condition


def execute() -> None:
	if frappe.db.exists("Workflow", "UTP Workflow"):
		workflow = frappe.get_doc("Workflow", "UTP Workflow")
		workflow.send_email_alert = 1
		workflow.custom_group_workflow_action_emails = 1
		workflow.custom_group_interval_value = 1
		workflow.custom_group_interval_unit = "Days"
		workflow.custom_group_send_time = "08:00:00"
		workflow.custom_group_email_template = "Dinext Timesheet Workflow Digest"
		workflow.custom_attach_document_pdf = 0
		workflow.save(ignore_permissions=True)
	if frappe.db.exists("Workflow", "AFL Workflow"):
		workflow = frappe.get_doc("Workflow", "AFL Workflow")
		workflow.send_email_alert = 1
		workflow.custom_group_workflow_action_emails = 0
		workflow.custom_workflow_action_email_template = "Dinext Workflow Action"
		workflow.save(ignore_permissions=True)
	for transition in frappe.get_all(
		"Workflow Transition",
		filters={"parent": "UTP Workflow"},
		fields=["name", "condition"],
	):
		condition = migrate_condition(transition.condition)
		if condition != transition.condition:
			frappe.db.set_value(
				"Workflow Transition",
				transition.name,
				"condition",
				condition,
				update_modified=False,
			)
	for workflow_name in ("UTP Workflow", "AFL Workflow"):
		for state in frappe.get_all(
			"Workflow Document State",
			filters={"parent": workflow_name, "state": "Отклонено"},
			pluck="name",
		):
			frappe.db.set_value(
				"Workflow Document State",
				state,
				"next_action_email_template",
				"Dinext Workflow Correction",
				update_modified=False,
			)
	frappe.clear_cache(doctype="Workflow")
