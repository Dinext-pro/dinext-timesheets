/**
 * Submit Start / Stop / Edit (demodev sendTimesheet + timesheet_validation).
 * Validation from model (frm.ut / ts_positions), not DOM.
 */
import {
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
import { clearInvalidCells, setInvalidCells } from "./invalid-cells.js";

const SET_STATUS =
	"dinext_timesheets.dinext_timesheets.user_timesheet.api.set_timesheet_status";

const BTN_START = "Отправить на согласование";
const BTN_STOP = "Остановить воркфлоу";
const BTN_EDIT = "Вернуть на редактирование";

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

/** Why Start is blocked, or "" if can submit. */
function startButtonBlockReason(frm) {
	if (!hasPositionRows(frm)) {
		return __("Добавьте хотя бы одну позицию");
	}
	if (needsSaveBeforeSubmit(frm)) {
		return __("Сначала сохраните таймшит");
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
 * Start button: disabled + tooltip when empty / dirty / unsaved.
 * Uses .disabled (not prop) so title tooltip still works on hover.
 */
export function syncStartButtonState(frm) {
	const $btn = findCustomButton(frm, BTN_START);
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

function validateDayTotals(frm, errors) {
	const template = frm.template_doc;
	if (!template) {
		return;
	}
	const holidays = frm.ut?.holidays || frm.holidays || [];
	const dates = frm.ut?.dates || [];
	const summary = (buildSummaryRows(frm) || [])[0] || {};
	const minDelta = flt(template.minimum_hours);
	const maxDelta = flt(template.maximum_hours);

	let hasAnyHours = false;
	for (const date of dates) {
		const total = flt(summary[dayField(date)]) || 0;
		if (total > 0) {
			hasAnyHours = true;
		}
		if (isHoliday(holidays, date)) {
			continue;
		}
		const dayHours = dayNormHours(frm, date);
		const minHours = dayHours - minDelta;
		const maxHours = dayHours + maxDelta;
		if (total < minHours) {
			errors.push(`${date} не может быть менее ${minHours} часов.`);
		}
		if (total > maxHours) {
			errors.push(`${date} не может быть более ${maxHours} часов.`);
		}
	}

	if (!hasAnyHours && dates.length) {
		const needsPositions = dates.some((date) => {
			if (isHoliday(holidays, date)) {
				return false;
			}
			const minHours = dayNormHours(frm, date) - minDelta;
			return minHours > 0;
		});
		if (needsPositions) {
			errors.push("Добавьте позиции для согласования!");
		}
	}
}

function validatePositionRows(frm, posStatus, errors, invalidCells = []) {
	const dates = frm.ut?.dates || [];
	const rows = (frm.ut?.rows || []).filter((r) => r.rowType === "position");
	const updatedPositions = [];

	collectDuplicatePositionErrors(rows, errors, invalidCells);

	rows.forEach((row, idx) => {
		const line = idx + 1;
		const rowErrors = [];
		if (!row.project) {
			rowErrors.push(`Выберите проект в ${line}й строке!`);
			invalidCells.push({ rowId: row.id, field: FIELD_PROJECT });
		}
		if (!row.document_name) {
			rowErrors.push(`Выберите запрос или задачу в ${line}й строке!`);
			invalidCells.push({ rowId: row.id, field: FIELD_TASK });
		}
		if (!row.project_role) {
			rowErrors.push(`Выберите проектную роль в ${line}й строке!`);
			invalidCells.push({ rowId: row.id, field: FIELD_ROLE });
		}
		const total = sumDayHours(row, dates);
		if (!total) {
			rowErrors.push(`Укажите часы в ${line}й строке!`);
			invalidCells.push({ rowId: row.id, field: "total" });
		}

		const table = [];
		for (const date of dates) {
			const hours = flt(row[dayField(date)]) || 0;
			const description = String(row[descField(date)] || "").trim();
			if (hours > 0 || description) {
				table.push({ date, hours, description });
			}
			if (hours > 0 && !description && frm.template_doc?._is_mandatory) {
				rowErrors.push(
					`${date} по задаче ${
						row.document_label || row.document_name || line
					} не заполнено описание.`
				);
				invalidCells.push({ rowId: row.id, field: dayField(date) });
			}
		}

		errors.push(...rowErrors);
		if (rowErrors.length || row.isNew) {
			return;
		}

		updatedPositions.push({
			doctype: "User Timesheet Position",
			name: row.id,
			parent: frm.doc.name,
			user_timesheet: frm.doc.name,
			user: frm.doc.timesheet_from,
			document_type: row.document_type || "Task",
			document_name: row.document_name,
			project: row.project,
			project_role: row.project_role,
			status: posStatus,
			all_hours: total,
			reject_reason: "",
			table,
		});
	});

	return updatedPositions;
}

async function timesheetValidation(workflow, frm) {
	let errors = [];
	const invalidCells = [];
	let posStatus = "На согласовании";
	if (workflow === "Stop" || workflow === "Edit") {
		posStatus = "Редактирование";
	}

	if (workflow === "Start") {
		const limitCheck = await checkPlannedHoursAndLimits(frm);
		errors.push(...(limitCheck.errors || []));
	}

	const updatedPositions = validatePositionRows(
		frm,
		posStatus,
		errors,
		invalidCells
	);
	if (workflow === "Start") {
		validateDayTotals(frm, errors);
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
		frappe.msgprint(__("Сначала сохраните таймшит"));
		return;
	}

	let tsStatus = "На согласовании";
	let posStatus = "На согласовании";
	let showErrors = true;
	if (workflow === "Stop" || workflow === "Edit") {
		tsStatus = "На доработке";
		posStatus = "Редактирование";
		showErrors = false;
	}

	try {
		const validation = await timesheetValidation(workflow, frm);
		const errors = validation.errors_passed || [];
		const updatedPositions = validation.updatedPositions || [];

		if (showErrors && errors.length) {
			setInvalidCells(frm, validation.invalidCells || []);
			frappe.msgprint({
				title: __("Ошибки заполнения ТШ:<br>"),
				indicator: "red",
				as_list: true,
				message: errors,
				primary_action: {
					label: __("Исправить"),
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
					"Ошибка при обработке позиций ТШ. Пожалуйста, обновите страницу и попробуйте заново."
				)
			);
			return;
		}

		frm.disable_save();

		if (updatedPositions.length > 0) {
			await frappe.call({
				method: SET_STATUS,
				args: {
					ts_name: frm.doc.name,
					ts_status: tsStatus,
					positions: updatedPositions,
					pos_status: posStatus,
				},
				silent: true,
				freeze: true,
				freeze_message: __("Сохранение..."),
			});
		} else {
			await frappe.db.set_value(
				"User Timesheet",
				frm.doc.name,
				"ut_status",
				workflow === "Edit" ? "На доработке" : "Согласован"
			);
		}

		frappe.show_alert(
			{ message: __("Данные успешно сохранены"), indicator: "green" },
			5
		);
		frm.reload_doc();
	} catch (error) {
		console.error("[UserTimesheet] sendTimesheet", error);
		const message =
			error?.message ||
			error?.exc ||
			error?.responseJSON?.exception ||
			String(error);
		frappe.msgprint({
			title: __("Ошибка обработки ТШ"),
			indicator: "red",
			message,
		});
	}
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

	const status = frm.doc.ut_status;
	const isOwner = frappe.session.user === frm.doc.timesheet_from;

	if (status === "Черновик" || status === "На доработке") {
		frm.add_custom_button(BTN_START, async () => {
			if (startButtonBlockReason(frm)) {
				syncStartButtonState(frm);
				return;
			}
			await sendTimesheet("Start", frm);
		});
		syncStartButtonState(frm);
	} else if (status === "На согласовании") {
		if (isOwner) {
			frm.add_custom_button(BTN_STOP, async () => {
				await sendTimesheet("Stop", frm);
			});
		}
	} else {
		frm.add_custom_button(BTN_EDIT, async () => {
			if (status === "Согласован") {
				frappe.warn(
					"Вы уверены, что хотите вернуть ТШ на редактирование?",
					__("Потребуется повторное согласование всего таймшита!"),
					async () => {
						await sendTimesheet("Edit", frm);
					},
					__("Продолжить"),
					true
				);
			} else {
				await sendTimesheet("Edit", frm);
			}
		});
	}
}

export { sendTimesheet };
