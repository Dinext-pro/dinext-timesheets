/**
 * Approver actions on the User Timesheet form.
 * Position workflow actions: get_timesheet_position_actions + apply_timesheet_position_action.
 */
import { guardEditableTimesheet, reportTimesheetError } from "./submit.js";
const POSITION_ACTIONS =
	"dinext_timesheets.workflow_approval.get_timesheet_position_actions";
const APPLY = "dinext_timesheets.workflow_approval.apply_timesheet_position_action";

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
		if (!(await guardEditableTimesheet(frm, transition))) {
			return;
		}
		let result;
		try {
			result = await frappe.xcall(APPLY, {
				timesheet_name: frm.doc.name,
				action: transition.action,
				comment,
				request_id: requestId(),
			});
		} catch (error) {
			reportTimesheetError(frm, error);
			return;
		}
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
	const ask = () => {
		if (!transition.comment_is_required) {
			return submit();
		}
		return promptForComment();
	};
	if (transition.confirm_return_to_editing) {
		frappe.warn(
			__("Are you sure you want to return the timesheet to editing?"),
			__("The entire timesheet will need to be re-approved!"),
			() => ask(),
			__("Continue"),
			true
		);
		return;
	}
	return ask();

	function promptForComment() {
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
}

/** Position workflow actions the current user can apply. */
export async function processUTWorkflow(frm) {
	const gen = (frm._ut_wf_gen = (frm._ut_wf_gen || 0) + 1);
	clearWorkflowButtons(frm);
	if (!frm || frm.is_new() || frm.doc?.__islocal) {
		return;
	}

	const response = await frappe
		.xcall(POSITION_ACTIONS, { timesheet_name: frm.doc.name })
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
