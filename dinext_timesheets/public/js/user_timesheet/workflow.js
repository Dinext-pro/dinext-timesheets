/**
 * Approver actions on UT Form (demodev UT_Accept_WF).
 */
const SET_STATUS =
	"dinext_timesheets.dinext_timesheets.user_timesheet.api.set_timesheet_status";

const ICONS = {
	Согласовано: "✅",
	"Не согласовано": "❌",
};

function workflowButtonLabel(action) {
	const icon = ICONS[action];
	return (icon ? `${icon} ` : "") + __(action);
}

export function clearWorkflowButtons(frm) {
	for (const label of frm._ut_wf_button_labels || []) {
		frm.remove_custom_button(label);
		frm.remove_custom_button(__(label));
	}
	frm._ut_wf_button_labels = [];
}

async function addUTComment(docname, comment) {
	const currentUser = frappe.session.user;
	return frappe.call({
		method: "frappe.desk.form.utils.add_comment",
		args: {
			reference_doctype: "User Timesheet Position",
			reference_name: docname,
			content: comment,
			comment_by: currentUser,
			comment_email: currentUser,
		},
		silent: true,
	});
}

async function updateUTPositions(frm, updatedPositions, pos_status, comment = null) {
	try {
		await frappe.call({
			method: SET_STATUS,
			args: {
				positions: updatedPositions,
				pos_status,
				ts_name: frm.doc.name,
			},
			silent: true,
			freeze: true,
			freeze_message: __("Saving data..."),
		});
		if (comment) {
			for (const item of updatedPositions) {
				await addUTComment(item.name, comment);
			}
		}
		frappe.show_alert(
			{ message: __("Data saved"), indicator: "green" },
			5
		);
		frm.reload_doc();
	} catch (err) {
		const message = err?.responseJSON?.exception || String(err);
		frappe.throw(__("Error saving data: {0}", [message]));
	}
}

/** Show common UTP workflow actions for current approver. */
export async function processUTWorkflow(frm) {
	const gen = (frm._ut_wf_gen = (frm._ut_wf_gen || 0) + 1);
	clearWorkflowButtons(frm);

	const isOwner = frappe.session.user === frm.doc.timesheet_from;
	if (isOwner || frm.doc.ut_status !== "На согласовании") {
		return;
	}
	if (!frm.ts_positions?.length) {
		return;
	}

	const positionNames = frm.ts_positions.map((pos) => pos.name);
	const userTasks = await frappe.db.get_list("Workflow Task", {
		fields: ["name", "wt_docname"],
		filters: {
			doc: "User Timesheet Position",
			wt_docname: ["in", positionNames],
			status: "Working",
			_assign: ["like", `%${frappe.session.user}%`],
		},
	});
	if (gen !== frm._ut_wf_gen) {
		return;
	}
	if (!userTasks.length) {
		return;
	}

	const taskPositionMap = {};
	userTasks.forEach((task) => {
		taskPositionMap[task.wt_docname] = task;
	});
	const positionsWithActiveTasks = frm.ts_positions.filter(
		(pos) => taskPositionMap[pos.name]
	);
	if (!positionsWithActiveTasks.length) {
		return;
	}
	frm.ts_positions_with_active_tasks = positionsWithActiveTasks;

	const actions = await frappe.xcall(
		"frappe.model.workflow.get_common_transition_actions",
		{
			docs: positionsWithActiveTasks,
			doctype: "User Timesheet Position",
		}
	);
	if (gen !== frm._ut_wf_gen) {
		return;
	}

	clearWorkflowButtons(frm);
	frm._ut_wf_button_labels = [];
	for (const action of actions || []) {
		const label = workflowButtonLabel(action);
		frm.add_custom_button(label, async () => {
			const position = { ...positionsWithActiveTasks[0] };
			position.doctype = "User Timesheet Position";
			const transitions = await frappe.workflow.get_transitions(position);
			const cur_transition = transitions.find((t) => t.action === action);
			if (!cur_transition) {
				return;
			}
			if (cur_transition.custom_comment_is_required) {
				frappe.prompt(
					{
						fieldtype: "Data",
						label: __("Enter a comment"),
						fieldname: "comment",
						reqd: 1,
					},
					async (data) => {
						await updateUTPositions(
							frm,
							positionsWithActiveTasks,
							cur_transition.next_state,
							data.comment
						);
					},
					`${__("Comment for action")} "${cur_transition.action}"`,
					__("Save")
				);
			} else {
				await updateUTPositions(
					frm,
					positionsWithActiveTasks,
					cur_transition.next_state
				);
			}
		});
		frm._ut_wf_button_labels.push(label);
	}
}
