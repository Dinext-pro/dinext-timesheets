/**
 * Submit Start / Stop / Edit (demodev sendTimesheet + timesheet_validation).
 * Validation from model (frm.ut / ts_positions), not DOM.
 */
import {
	canEdit,
	collectDuplicatePositionErrors,
	dayField,
	descField,
	isHoliday,
	sumDayHours,
	syncPositionFromRow,
} from "./model.js";
import { checkPlannedHoursAndLimits } from "./limits.js";
import { buildSummaryRows } from "./summary.js";
import {
	FIELD_PROJECT,
	FIELD_ROLE,
	FIELD_TASK,
} from "./editors/cascade-commit.js";
import { clearInvalidCells, setInvalidCells, SUMMARY_ROW_ID } from "./invalid-cells.js";

const ORCHESTRATE = "dinext_timesheets.workflow_approval.orchestrate_timesheet";

const BTN_START = "Submit for Approval";
const BTN_STOP = "Stop Workflow";
const BTN_EDIT = "Return to Editing";

function syncAllRows(frm) {
	for (const row of frm.ut?.rows || []) {
		if (row.rowType === "position") {
			syncPositionFromRow(frm, row);
		}
	}
}

function hasUnsavedPositions(frm) {
	const positions = frm.ts_positions || [];
	if ((frm.deletedPositions || []).length) {
		return true;
	}
	return positions.some((p) => p.new || String(p.name || "").startsWith("new_"));
}

function needsSaveBeforeSubmit(frm) {
	return !!(hasUnsavedPositions(frm) || frm.is_dirty?.());
}

function hasPositionRows(frm) {
	return (frm.ut?.rows || []).some((r) => r.rowType === "position");
}

function hasLeaveRows(frm) {
	return (frm.ut?.rows || []).some((r) => r.rowType === "leave");
}

/** Positions or leave make a day-total row. Empty sheet has neither. */
function hasDayGrid(frm) {
	return hasPositionRows(frm) || hasLeaveRows(frm);
}

/** Why Start is blocked, or "" if can submit. Hours are the validator's job. */
function startButtonBlockReason(frm) {
	if (needsSaveBeforeSubmit(frm)) {
		return __("Save the timesheet first");
	}
	return "";
}

function findCustomButton(frm, label) {
	const encoded = encodeURIComponent(label);
	return $(frm.page?.wrapper || frm.$wrapper).find(
		`button[data-label="${encoded}"], .btn[data-label="${encoded}"]`
	);
}

/**
 * Start button: disabled + tooltip when dirty / unsaved.
 * Uses .disabled (not prop) so title tooltip still works on hover.
 */
export function syncStartButtonState(frm) {
	const $btn = findCustomButton(frm, __(BTN_START));
	if (!$btn.length) {
		return;
	}
	const reason = startButtonBlockReason(frm);
	const blocked = !!reason;
	$btn.toggleClass("disabled ut-btn--need-save", blocked);
	$btn.attr("aria-disabled", blocked ? "true" : "false");
	$btn.attr("title", reason);
}

function bindStartButtonDirtySync(frm) {
	if (!frm?.$wrapper || frm.ut?._startBtnDirtyBound) {
		return;
	}
	if (frm.ut) {
		frm.ut._startBtnDirtyBound = true;
	}
	frm.$wrapper.on("dirty.utStartBtn", () => {
		syncStartButtonState(frm);
	});
}

function dayNormHours(frm, date) {
	const reduced = (frm.ut?.workHours || []).find((d) => d.wht_date === date);
	if (reduced && reduced.wht_hours != null && reduced.wht_hours !== "") {
		return flt(reduced.wht_hours);
	}
	return flt(frm.template_doc?.hours_on_date) || 0;
}

function validateEmptyPeriod(frm, dates, holidays, minDelta, errors) {
	const needsPositions = dates.some((date) => {
		if (isHoliday(holidays, date)) {
			return false;
		}
		return dayNormHours(frm, date) - minDelta > 0;
	});
	if (needsPositions) {
		errors.push(__("Add positions for approval"));
	}
}

function validateDayTotals(frm, errors, invalidCells = []) {
	const template = frm.template_doc;
	if (!template) {
		return;
	}
	const holidays = frm.ut?.holidays || frm.holidays || [];
	const dates = frm.ut?.dates || [];
	const minDelta = flt(template.minimum_hours);
	const maxDelta = flt(template.maximum_hours);

	if (!hasDayGrid(frm)) {
		validateEmptyPeriod(frm, dates, holidays, minDelta, errors);
		return;
	}

	const summary = (buildSummaryRows(frm) || [])[0] || {};
	for (const date of dates) {
		if (isHoliday(holidays, date)) {
			continue;
		}
		const total = flt(summary[dayField(date)]) || 0;
		const dayHours = dayNormHours(frm, date);
		const minHours = dayHours - minDelta;
		const maxHours = dayHours + maxDelta;
		if (total < minHours) {
			const message = __("{0} cannot be less than {1} hours.", [date, minHours]);
			errors.push(message);
			invalidCells.push({
				rowId: SUMMARY_ROW_ID,
				field: dayField(date),
				message,
			});
		}
		if (total > maxHours) {
			const message = __("{0} cannot be more than {1} hours.", [date, maxHours]);
			errors.push(message);
			invalidCells.push({
				rowId: SUMMARY_ROW_ID,
				field: dayField(date),
				message,
			});
		}
	}
}

function orchestrationPosition(frm, row) {
	const dates = frm.ut?.dates || [];
	const name = String(row.id || "");
	const isNew = !!(row.isNew || name.startsWith("new_") || /^\d+$/.test(name));
	const table = [];
	for (const date of dates) {
		const hours = flt(row[dayField(date)]) || 0;
		const description = String(row[descField(date)] || "").trim();
		if (hours > 0 || description) {
			table.push({ date, hours, description });
		}
	}
	return {
		name,
		new: isNew,
		project: row.project || "",
		document_type: row.document_type || "Task",
		document_name: row.document_name || "",
		project_role: row.project_role || "",
		table,
	};
}

function validatePositionRows(frm, errors, invalidCells = []) {
	const dates = frm.ut?.dates || [];
	const rows = (frm.ut?.rows || []).filter((r) => r.rowType === "position");
	const updatedPositions = [];

	collectDuplicatePositionErrors(rows, errors, invalidCells);

	rows.forEach((row, idx) => {
		const line = idx + 1;
		const rowErrors = [];
		if (!row.project) {
			const message = __("Select a project in row {0}", [line]);
			rowErrors.push(message);
			invalidCells.push({ rowId: row.id, field: FIELD_PROJECT, message });
		}
		if (!row.document_name) {
			const message = __("Select a request or task in row {0}", [line]);
			rowErrors.push(message);
			invalidCells.push({ rowId: row.id, field: FIELD_TASK, message });
		}
		if (!row.project_role) {
			const message = __("Select a project role in row {0}", [line]);
			rowErrors.push(message);
			invalidCells.push({ rowId: row.id, field: FIELD_ROLE, message });
		}
		const total = sumDayHours(row, dates);
		if (!total) {
			const message = __("Enter hours in row {0}", [line]);
			rowErrors.push(message);
			invalidCells.push({ rowId: row.id, field: "total", message });
		}

		for (const date of dates) {
			const hours = flt(row[dayField(date)]) || 0;
			const description = String(row[descField(date)] || "").trim();
			if (hours > 0 && !description && frm.template_doc?._is_mandatory) {
				const message = __(
					"Description is not filled for {0} on task {1}",
					[date, row.document_label || row.document_name || line]
				);
				rowErrors.push(message);
				invalidCells.push({
					rowId: row.id,
					field: dayField(date),
					message,
				});
			}
		}

		errors.push(...rowErrors);
		if (rowErrors.length || row.isNew) {
			return;
		}

		updatedPositions.push(orchestrationPosition(frm, row));
	});

	return updatedPositions;
}

async function timesheetValidation(workflow, frm) {
	let errors = [];
	const invalidCells = [];

	if (workflow === "Start") {
		const limitCheck = await checkPlannedHoursAndLimits(frm);
		errors.push(...(limitCheck.errors || []));
	}

	const updatedPositions = validatePositionRows(frm, errors, invalidCells);
	if (workflow === "Start") {
		validateDayTotals(frm, errors, invalidCells);
	}

	if (errors.length) {
		errors = [...new Set(errors)];
	}

	return { errors_passed: errors, updatedPositions, invalidCells };
}

async function sendTimesheet(workflow, frm) {
	syncAllRows(frm);

	if (workflow === "Start" && startButtonBlockReason(frm)) {
		/* Button should already be disabled; keep guard for safety. */
		syncStartButtonState(frm);
		return;
	}
	if (workflow !== "Start" && needsSaveBeforeSubmit(frm)) {
		frappe.msgprint(__("Save the timesheet first"));
		return;
	}

	let showErrors = true;
	if (workflow === "Stop" || workflow === "Edit") {
		showErrors = false;
	}

	try {
		const validation = await timesheetValidation(workflow, frm);
		const errors = validation.errors_passed || [];
		const updatedPositions = validation.updatedPositions || [];

		if (showErrors && errors.length) {
			setInvalidCells(frm, validation.invalidCells || []);
			frappe.msgprint({
				title: __("Timesheet Validation Errors"),
				indicator: "red",
				as_list: true,
				message: errors,
				primary_action: {
					label: __("Fix"),
					action() {
						frappe.msg_dialog?.cancel?.();
					},
				},
			});
			return;
		}

		clearInvalidCells(frm);

		const expected = (frm.ts_positions || []).filter(
			(p) => !String(p.name || "").startsWith("new_")
		).length;
		if (updatedPositions.length !== expected) {
			frappe.msgprint(
				__(
					"Error processing timesheet positions. Please refresh the page and try again."
				)
			);
			return;
		}

		frm.disable_save();

		await frappe.call({
			method: ORCHESTRATE,
			args: {
				ts_name: frm.doc.name,
				operation: workflow,
				positions: updatedPositions,
				deleted_positions: frm.deletedPositions || [],
			},
			silent: true,
			freeze: true,
			freeze_message: __("Saving..."),
		});
		frm.deletedPositions = [];

		frappe.show_alert(
			{ message: __("Data saved successfully"), indicator: "green" },
			5
		);
		frm.reload_doc();
	} catch (error) {
		console.error("[UserTimesheet] sendTimesheet", error);
		reportTimesheetError(frm, error);
	} finally {
		frm.enable_save();
	}
}

function reportTimesheetError(frm, error) {
	const excType = error?.responseJSON?.exc_type;
	if (frappe.boot?.error_report_email && excType !== "ValidationError") {
		const body = [
			`<h4>${__("Timesheet processing error report")}</h4>`,
			`<h5>${__(
				"Add any details that would help support reproduce the problem:"
			)}</h5>`,
			'<div style="min-height: 100px; border: 1px solid #bbb; border-radius: 5px; padding: 15px; margin-bottom: 15px;"></div>',
			"<hr>",
			`<h5>${__("Timesheet")}</h5>`,
			`<pre>${frappe.utils.escape_html(frm.docname || frm.doc?.name || "")}</pre>`,
			"<hr>",
			`<h5>${__("Error")}</h5>`,
			`<pre>${frappe.utils.escape_html(String(error))}</pre>`,
		].join("\n");
		new frappe.views.CommunicationComposer({
			subject: `${__("Timesheet processing error")} [${frappe.datetime.nowdate()}]`,
			recipients: frappe.boot.error_report_email,
			message: body,
		});
		return;
	}
	frappe.msgprint({
		title: __("Error saving timesheet"),
		indicator: "red",
		message:
			error?.responseJSON?.exception ||
			error?.message ||
			String(error),
	});
}

export function clearSubmitButtons(frm) {
	for (const label of [BTN_START, BTN_STOP, BTN_EDIT]) {
		frm.remove_custom_button(label);
		frm.remove_custom_button(__(label));
	}
}

/** Form custom buttons Start / Stop / Edit by ut_status. */
export function setupSubmitButtons(frm) {
	if (!frm || frm.is_new() || frm.doc?.__islocal) {
		return;
	}

	clearSubmitButtons(frm);
	bindStartButtonDirtySync(frm);
	if ((frm._ut_wf_button_labels || []).length) {
		return;
	}

	const status = frm.doc.ut_status;

	if (status === "Draft" || status === "Rework") {
		frm.add_custom_button(__(BTN_START), async () => {
			if (startButtonBlockReason(frm)) {
				syncStartButtonState(frm);
				return;
			}
			await sendTimesheet("Start", frm);
		});
		syncStartButtonState(frm);
	} else if (status === "Pending Approval") {
		// Stop is a workflow-menu action. A second button would duplicate it.
	} else {
		frm.add_custom_button(__(BTN_EDIT), async () => {
			if (status === "Approved") {
				frappe.warn(
					__("Are you sure you want to return the timesheet to editing?"),
					__("The entire timesheet will need to be re-approved!"),
					async () => {
						await sendTimesheet("Edit", frm);
					},
					__("Continue"),
					true
				);
			} else {
				await sendTimesheet("Edit", frm);
			}
		});
	}
}

export async function guardEditableTimesheet(frm) {
	if (!canEdit(frm)) {
		return true;
	}
	syncAllRows(frm);
	if (needsSaveBeforeSubmit(frm)) {
		frappe.msgprint(__("Save the timesheet first"));
		return false;
	}
	const validation = await timesheetValidation("Start", frm);
	const errors = validation.errors_passed || [];
	if (errors.length) {
		setInvalidCells(frm, validation.invalidCells || []);
		frappe.msgprint({
			title: __("Timesheet Validation Errors"),
			indicator: "red",
			as_list: true,
			message: errors,
			primary_action: {
				label: __("Fix"),
				action() {
					frappe.msg_dialog?.cancel?.();
				},
			},
		});
		return false;
	}
	clearInvalidCells(frm);
	return true;
}

export { sendTimesheet };
