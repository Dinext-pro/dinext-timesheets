"""Correct and complete Workflow settings after metadata field stabilization."""

import frappe


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
		if not any(
			row.role == "Dinext_UT_Full_Access"
			for row in workflow.custom_approval_monitor_roles
		):
			workflow.append(
				"custom_approval_monitor_roles",
				{"role": "Dinext_UT_Full_Access"},
			)
		workflow.save(ignore_permissions=True)
	if frappe.db.exists("Workflow", "AFL Workflow"):
		workflow = frappe.get_doc("Workflow", "AFL Workflow")
		workflow.send_email_alert = 1
		workflow.custom_group_workflow_action_emails = 0
		workflow.custom_workflow_action_email_template = "Dinext Workflow Action"
		if not any(
			row.role == "Dinext_UT_Full_Access"
			for row in workflow.custom_approval_monitor_roles
		):
			workflow.append(
				"custom_approval_monitor_roles",
				{"role": "Dinext_UT_Full_Access"},
			)
		workflow.save(ignore_permissions=True)
	for transition in frappe.get_all(
		"Workflow Transition",
		filters={"parent": "UTP Workflow"},
		fields=["name", "action", "condition"],
	):
		values = {}
		if "Z_Dinord_Team_Lead" in (transition.condition or ""):
			values["condition"] = transition.condition.replace(
				"Z_Dinord_Team_Lead",
				"Dinext_Team_Lead",
			)
		if transition.action == "Согласовано":
			values["custom_auto_complete_unchanged"] = 1
		if values:
			frappe.db.set_value(
				"Workflow Transition",
				transition.name,
				values,
				update_modified=False,
			)
	for transition in frappe.get_all(
		"Workflow Transition",
		filters={"parent": "AFL Workflow", "next_state": "Отклонено"},
		pluck="name",
	):
		frappe.db.set_value(
			"Workflow Transition",
			transition,
			"custom_comment_is_required",
			1,
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
	for card_name in (
		"Заявки на отсутствие согласованные мной-1",
		"Заявки на отсутствие у меня на согласовании-2",
		"ТШ согласованные мной-1",
		"ТШ у меня на согласовании-2",
	):
		if frappe.db.exists("Number Card", card_name):
			frappe.db.set_value(
				"Number Card",
				card_name,
				"method",
				"dinext_common.workflow_approval.api.get_legacy_number_card_result",
				update_modified=False,
			)
	_ensure_workflow_task_permissions()


def _ensure_workflow_task_permissions() -> None:
	deny_mutations = {
		"write": 0,
		"create": 0,
		"delete": 0,
		"submit": 0,
		"cancel": 0,
		"amend": 0,
		"email": 0,
		"print": 0,
		"share": 0,
	}
	permissions = {
		"All": {
			**deny_mutations,
			"read": 1,
			"if_owner": 0,
			"select": 1,
			"export": 0,
			"report": 1,
		},
		"Dinext_User": {
			**deny_mutations,
			"read": 1,
			"if_owner": 1,
			"select": 0,
			"export": 0,
			"report": 0,
		},
		"Dinext_UTP_Appoval": {
			**deny_mutations,
			"read": 0,
			"if_owner": 0,
			"select": 1,
			"export": 0,
			"report": 0,
		},
		"Dinext_UT_Full_Access": {
			**deny_mutations,
			"read": 1,
			"if_owner": 0,
			"select": 1,
			"report": 1,
			"export": 1,
		},
	}
	legacy_names = ("cdi70531d5", "g2rmhjbeg2", "g70iffqseh")
	for role, values in permissions.items():
		if frappe.get_all(
			"Custom DocPerm",
			filters={
				"parent": "Workflow Task",
				"role": role,
				"permlevel": 0,
				"name": ("not in", legacy_names),
			},
			limit=1,
		):
			existing = frappe.get_doc(
				"Custom DocPerm",
				frappe.get_all(
					"Custom DocPerm",
					filters={
						"parent": "Workflow Task",
						"role": role,
						"permlevel": 0,
						"name": ("not in", legacy_names),
					},
					pluck="name",
					limit=1,
				)[0],
			)
			existing.update(values)
			existing.save(ignore_permissions=True)
			continue
		frappe.get_doc(
			{
				"doctype": "Custom DocPerm",
				"parent": "Workflow Task",
				"role": role,
				"permlevel": 0,
				**values,
			}
		).insert(ignore_permissions=True)
