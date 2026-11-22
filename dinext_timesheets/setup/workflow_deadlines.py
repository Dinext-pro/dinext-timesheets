"""Install the UTP escalation policy without overwriting subsequent user edits."""

import frappe

MARKER = "dinext_utp_deadline_profile_v1"


def configure_utp_deadlines():
	if frappe.db.get_default(MARKER) or not frappe.db.exists("Workflow", "UTP Workflow"):
		return
	workflow = frappe.get_doc("Workflow", "UTP Workflow")
	for row in workflow.transitions:
		if row.state == "Pending Approval" and row.next_state == "Approved":
			row.update(
				dict(
					custom_deadline_enabled=1,
					custom_deadline_value=3,
					custom_deadline_unit="Working Days",
					custom_deadline_recipient_type="Worker Group Manager",
					custom_deadline_email_mode="Digest",
					custom_deadline_email_template="Dinext Timesheet Workflow Deadline Digest",
					custom_deadline_interval_unit="Days",
					custom_deadline_interval_value=1,
					custom_deadline_send_times="08:00, 17:00",
				)
			)
	workflow.save(ignore_permissions=True)
	from dinext_common.workflow_approval.deadlines.backfill import backfill_open_tasks

	result = backfill_open_tasks(workflow.name)
	frappe.db.set_default(MARKER, 1)
	return result
