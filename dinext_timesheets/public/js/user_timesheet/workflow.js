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

/** New or Not Saved: same flag as the orange form pill. */
function timesheetNeedsSave(frm) {
	return !!(frm?.is_new?.() || frm?.doc?.__islocal || frm?.is_dirty?.());
}

function bindUnsavedWorkflowHide(frm) {
	if (!frm?.$wrapper || frm._ut_wf_dirty_bound) {
		return;
	}
	frm._ut_wf_dirty_bound = true;
	frm.$wrapper.on("dirty.utWorkflow", () => {
		frm._ut_wf_gen = (frm._ut_wf_gen || 0) + 1;
		clearWorkflowButtons(frm);
	});
}

async function refreshTimesheet(frm) {
	let finishRefresh;
	let timer;
	const refreshed = new Promise((resolve, reject) => {
		finishRefresh = resolve;
		timer = setTimeout(() => reject(new Error(__("Could not reload the workflow document"))), 30000);
	});
	frm._ut_wait_for_workflow_refresh = finishRefresh;
	try {
		frm.refresh();
		await refreshed;
	} finally {
		clearTimeout(timer);
		if (frm._ut_wait_for_workflow_refresh === finishRefresh) {
			frm._ut_wait_for_workflow_refresh = null;
		}
	}
}

function applyTimesheetAction(frm, transition) {
	const {
		captureWorkflowForm,
		reloadWorkflowForm,
		runWorkflowOperation,
		withWorkflowComment,
		workflowRequest,
	} = frappe.dinext;
	const target = captureWorkflowForm(frm);
	const submit = async (comment) => {
		if (!target.isCurrent()) return;
		const id = requestId();
		const count = transition.positions?.length || 1;
		let result;
		let validationMessage;
		try {
			result = await runWorkflowOperation(frm.page, async (updateProgress) => {
				if (!(await guardEditableTimesheet(frm, transition, (message) => {
					validationMessage = message;
				}))) {
					return;
				}
				if (!target.isCurrent()) return;
				const outcome = await workflowRequest(APPLY, {
					timesheet_name: target.name,
					action: transition.action,
					comment,
					request_id: id,
					track_progress: count > 1,
				});
				if (!outcome) {
					throw new Error(__("The workflow result could not be confirmed"));
				}
				updateProgress(outcome.processed, outcome.total);
				if (target.isCurrent()) {
					await reloadWorkflowForm(frm, () => refreshTimesheet(frm));
				}
				return outcome;
			}, {
				count,
				title: frappe.utils.escape_html(__("Applying: {0}", [__(transition.action)])),
				requestId: id,
			});
		} catch (error) {
			reportTimesheetError(frm, error);
			return;
		}
		if (validationMessage) {
			frappe.msgprint(validationMessage);
		}
		if (!result) return;

		const results = result.results || [];
		const messages = result.messages || [];
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
		} else if (messages.length) {
			frappe.msgprint({
				indicator: "orange",
				message: messageHtml,
			});
		}
	};
	const ask = () => withWorkflowComment(transition, submit);
	if (transition.confirm_return_to_editing) {
		frappe.warn(
			__("Are you sure you want to return the timesheet to editing?"),
			__("The entire timesheet will need to be re-approved!"),
			ask,
			__("Continue"),
			true
		);
		return;
	}
	return ask();
}

/** Position workflow actions the current user can apply. */
export async function processUTWorkflow(frm) {
	if (!frm) {
		return;
	}
	const gen = (frm._ut_wf_gen = (frm._ut_wf_gen || 0) + 1);
	clearWorkflowButtons(frm);
	bindUnsavedWorkflowHide(frm);
	if (timesheetNeedsSave(frm)) {
		return;
	}

	const response = await frappe.dinext
		.workflowRequest(POSITION_ACTIONS, { timesheet_name: frm.doc.name })
		.catch(() => null);
	if (gen !== frm._ut_wf_gen || timesheetNeedsSave(frm)) {
		return;
	}

	frm._ut_wf_button_labels = [];
	for (const transition of response?.actions || []) {
		const label =
			frappe.dinext?.workflowTransitionLabel?.(transition) ||
			frappe.dinext?.workflowActionLabel?.(transition.action) || __(transition.action);
		frm.add_custom_button(
			label,
			() => applyTimesheetAction(frm, transition),
			__(WORKFLOW_GROUP)
		);
		frm._ut_wf_button_labels.push(label);
	}
}
