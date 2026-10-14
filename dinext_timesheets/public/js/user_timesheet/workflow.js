/**
 * Approver actions on the User Timesheet form.
 * Parallel engine: get_timesheet_approval_actions + vote_timesheet_positions.
 */
import { guardEditableTimesheet } from "./submit.js";
const APPROVAL_ACTIONS =
	"dinext_timesheets.workflow_approval.get_timesheet_approval_actions";
const VOTE = "dinext_timesheets.workflow_approval.vote_timesheet_positions";

const WORKFLOW_GROUP = "Workflow";

function requestId() {
	return (
		window.crypto?.randomUUID?.() ||
		`${Date.now()}-${Math.random().toString(16).slice(2)}`
	);
}

export function clearWorkflowButtons(frm) {
	const group = __(WORKFLOW_GROUP);
	for (const label of frm._ut_wf_button_labels || []) {
		frm.remove_custom_button(label, group);
		frm.remove_custom_button(__(label), group);
		frm.remove_custom_button(label);
		frm.remove_custom_button(__(label));
	}
	frm._ut_wf_button_labels = [];
}

function applyTimesheetAction(frm, transition) {
	const submit = async (comment = "") => {
		if (!(await guardEditableTimesheet(frm))) {
			return;
		}
		const result = await frappe.xcall(VOTE, {
			timesheet_name: frm.doc.name,
			action: transition.action,
			comment,
			request_id: requestId(),
		});
		const results = result?.results || [];
		const messages = result?.messages || [];
		const transitioned = results.some((row) => row.transitioned);
		const failed = results.some(
			(row) =>
				!row.transitioned &&
				["Conflicted", "Stalled"].includes(row.round_status)
		);
		const messageHtml = messages
			.map((message) => frappe.utils.escape_html(message))
			.join("<br>");
		if (!transitioned && (failed || messages.length)) {
			frappe.msgprint({
				title: __("Workflow action was not applied"),
				indicator: "red",
				message: messageHtml || __("Workflow action was not applied"),
			});
			await frm.reload_doc();
			return;
		}
		if (messages.length) {
			frappe.msgprint({
				indicator: "orange",
				message: messageHtml,
			});
			await frm.reload_doc();
			return;
		}
		frappe.show_alert({
			message: __("Workflow action recorded"),
			indicator: transitioned ? "green" : "blue",
		});
		await frm.reload_doc();
	};
	if (!transition.comment_is_required) {
		return submit();
	}
	frappe.prompt(
		[
			{
				fieldname: "comment",
				fieldtype: "Small Text",
				label: __("Comment"),
				reqd: 1,
			},
		],
		(values) => submit(values.comment),
		__("Comment required for {0}", [__(transition.action)]),
		__("Apply")
	);
}

/** Common approval actions for the current user, when parallel workflow is on. */
export async function processUTWorkflow(frm) {
	const gen = (frm._ut_wf_gen = (frm._ut_wf_gen || 0) + 1);
	clearWorkflowButtons(frm);
	if (!frm || frm.is_new() || frm.doc?.__islocal) {
		return;
	}
	if (!frappe.boot?.enable_parallel_workflow_approval) {
		return;
	}

	const response = await frappe
		.xcall(APPROVAL_ACTIONS, { timesheet_name: frm.doc.name })
		.catch(() => null);
	if (gen !== frm._ut_wf_gen) {
		return;
	}

	frm._ut_wf_button_labels = [];
	for (const transition of response?.actions || []) {
		const label =
			frappe.dinext?.workflowActionLabel?.(transition.action) || __(transition.action);
		frm.add_custom_button(
			label,
			() => applyTimesheetAction(frm, transition),
			__(WORKFLOW_GROUP)
		);
		frm._ut_wf_button_labels.push(label);
	}
}
