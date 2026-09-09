/**
 * Project → Task → Role as AG in-cell editor (Frappe Select).
 * Core owns click / arrows / Enter / F2. Auto-open next list only after commit.
 */
import { canEdit } from "../model.js";
import {
	buildProjectSelectOptions,
	buildTaskSelectOptions,
	projectOptionsForRow,
	resolveProjectOption,
	resolveTaskOption,
	roleOptionsForRow,
	taskOptionsForRow,
} from "../catalog.js";

export const FIELD_PROJECT = "project_label";
export const FIELD_TASK = "document_label";
export const FIELD_ROLE = "project_role";

const CASCADE_FIELDS = [FIELD_PROJECT, FIELD_TASK, FIELD_ROLE];

/** True while cascade editor GUI is mounted — skip refresh/fit that would unmount it. */
export function isCascadeSelectOpen() {
	return !!document.querySelector(".user-timesheet-table .ut-select-edit");
}

/** Row fields touched by cascade (display + ids). */
export const CASCADE_DATA_FIELDS = [
	"project",
	"project_label",
	"document_type",
	"document_name",
	"document_label",
	"project_role",
];

function ensureCatalog(frm) {
	const customers = frm.ut?.tasksData || frm.tasks_data;
	if (!customers || !Object.keys(customers).length) {
		frappe.msgprint(__("Список задач ещё не загружен"));
		return false;
	}
	return true;
}

function refreshCells(params, columns) {
	params.api?.refreshCells?.({
		rowNodes: params.node ? [params.node] : undefined,
		columns,
		force: true,
	});
}

function editSource() {
	return (
		(typeof DinextTable !== "undefined" &&
			DinextTable.CELL_CHANGE_SOURCES?.EDIT) ||
		"edit"
	);
}

/**
 * Canon path: one batch → validate → apply → onSaveCells → undo stack.
 * @returns {boolean}
 */
function commitCascadePatch(frm, params, patch) {
	const table = frm.ut?.table;
	const node = params?.node;
	const row = node?.data || params?.data;
	if (!table?.commitCellChanges || !node || !row) {
		console.error("[UserTimesheet] cascade: commitCellChanges unavailable");
		return false;
	}

	const changes = [];
	for (const field of Object.keys(patch)) {
		const newValue = patch[field];
		const oldValue = row[field];
		if ((oldValue ?? "") === (newValue ?? "")) {
			continue;
		}
		changes.push({
			node,
			field,
			oldValue,
			newValue,
			rowIndex: node.rowIndex,
			colId: field,
		});
	}
	if (!changes.length) {
		return false;
	}

	const { applied } = table.commitCellChanges({
		source: editSource(),
		changes,
		alreadyApplied: false,
	});
	return applied > 0;
}

function showNativeList(selectEl) {
	if (!selectEl || selectEl.tagName !== "SELECT") {
		return;
	}
	selectEl.focus({ preventScroll: true });
	if (typeof selectEl.showPicker === "function") {
		try {
			selectEl.showPicker();
			return;
		} catch (_err) {
			/* ignore */
		}
	}
	selectEl.click();
}

function buildProjectPatch(project) {
	const patch = {
		project: project.name,
		project_label: project.project_name || project.name,
		document_type: "Task",
		document_name: "",
		document_label: "",
		project_role: "",
	};
	const tasks = project.tasks_issues || [];
	const roles = project.roles || [];
	if (tasks.length === 1) {
		const t = tasks[0];
		patch.document_type = t.tsdoctype || "Task";
		patch.document_name = t.name;
		patch.document_label = t.subject || t.name;
	}
	if (roles.length === 1) {
		patch.project_role = roles[0];
	}
	return patch;
}

function buildTaskPatch(frm, row, task) {
	const patch = {
		document_type: task.tsdoctype || "Task",
		document_name: task.name,
		document_label: task.subject || task.name,
	};
	if (!row.project_role) {
		const roles = roleOptionsForRow(frm, row);
		if (roles.length === 1) {
			patch.project_role = roles[0];
		}
	}
	return patch;
}

function scheduleStartEdit(api, rowIndex, field) {
	if (!api || rowIndex == null || !field) {
		return;
	}
	/* After current editor teardown; timeout keeps change-gesture closer than rAF. */
	setTimeout(() => {
		api.ensureColumnVisible?.(field);
		api.setFocusedCell?.(rowIndex, field);
		api.startEditingCell?.({ rowIndex, colKey: field });
	}, 0);
}

/** Build options + display + commit. onCommit returns next field or null. */
function resolveField(frm, row, params, field) {
	if (field === FIELD_PROJECT) {
		const projects = projectOptionsForRow(frm, row);
		const mapped = buildProjectSelectOptions(projects);
		const current = mapped.find((m) => m.project.name === row.project);
		return {
			options: mapped.map((m) => ({
				value: m.value,
				label: m.option,
			})),
			displayValue: current?.value || row.project || "",
			onCommit: (next) => {
				const project = resolveProjectOption(projects, next);
				if (!project) {
					frappe.msgprint(__("Проект не найден"));
					refreshCells(params, [FIELD_PROJECT]);
					return null;
				}
				const patch = buildProjectPatch(project);
				if (!commitCascadePatch(frm, params, patch)) {
					refreshCells(params, [FIELD_PROJECT, FIELD_TASK, FIELD_ROLE]);
					return null;
				}
				if (patch.document_name && patch.project_role) {
					return null;
				}
				return patch.document_name ? FIELD_ROLE : FIELD_TASK;
			},
		};
	}

	if (field === FIELD_TASK) {
		if (!row.project) {
			return { needProject: true };
		}
		const tasks = taskOptionsForRow(frm, row);
		const mapped = buildTaskSelectOptions(tasks);
		const current = mapped.find((m) => m.task.name === row.document_name);
		return {
			options: mapped.map((m) => m.option),
			displayValue: current?.option || row.document_label || "",
			onCommit: (next) => {
				const task = resolveTaskOption(tasks, next);
				if (!task) {
					frappe.msgprint(__("Задача не найдена"));
					refreshCells(params, [FIELD_TASK]);
					return null;
				}
				const patch = buildTaskPatch(frm, row, task);
				if (!commitCascadePatch(frm, params, patch)) {
					refreshCells(params, [FIELD_TASK, FIELD_ROLE]);
					return null;
				}
				if (patch.project_role || row.project_role) {
					return null;
				}
				return FIELD_ROLE;
			},
		};
	}

	if (!row.project) {
		return { needProject: true };
	}
	const roles = roleOptionsForRow(frm, row);
	return {
		options: roles,
		displayValue: row.project_role || "",
		onCommit: (next) => {
			if (!commitCascadePatch(frm, params, { project_role: next })) {
				refreshCells(params, [FIELD_ROLE]);
			}
			return null;
		},
	};
}

/**
 * AG Grid in-cell editor. Core starts it (2nd click / Enter / F2 / startEditingCell).
 * Domain commit stays on commitCellChanges. AG write cancelled (display ≠ option key).
 */
export class CascadeSelectCellEditor {
	init(params) {
		this.params = params;
		this.frm = params.colDef?.cellEditorParams?.frm;
		this.field = params.colDef?.field;
		this._stopped = false;
		this._nextField = null;
		this._abort = false;
		this._needProject = false;
		this._empty = false;

		this.host = document.createElement("div");
		this.host.className = "ut-select-edit";

		const row = params.node?.data || params.data;
		if (!this.frm || !canEdit(this.frm) || !CASCADE_FIELDS.includes(this.field)) {
			this._abort = true;
			return;
		}
		if (!row || row.rowType !== "position") {
			this._abort = true;
			return;
		}
		if (!ensureCatalog(this.frm)) {
			this._abort = true;
			return;
		}

		const spec = resolveField(this.frm, row, params, this.field);
		if (spec.needProject) {
			this._needProject = true;
			return;
		}
		if (!spec.options?.length) {
			this._empty = true;
			return;
		}

		this._mountControl(spec);
	}

	_mountControl(spec) {
		const oldValue = spec.displayValue || "";
		const structured = spec.options.some((o) => o && typeof o === "object");
		const control = frappe.ui.form.make_control({
			parent: $(this.host),
			only_input: true,
			df: {
				fieldname: this.field,
				fieldtype: "Select",
				label: "",
				options: structured ? spec.options : spec.options.join("\n"),
			},
			render_input: true,
		});
		this._control = control;
		if (oldValue) {
			control.set_value(oldValue);
		}
		control.$wrapper?.addClass?.("ut-select-control");
		control.$wrapper?.find?.(".control-label, .help-box, .clearfix")?.hide?.();

		const selectEl = control.$input?.get?.(0);
		this._selectEl = selectEl;

		control.$input?.on?.("change", () => {
			if (this._stopped) {
				return;
			}
			const next = control.get_value();
			if (next != null && String(next) !== String(oldValue)) {
				this._nextField = spec.onCommit(String(next));
			}
			this.stopEditing();
		});
		control.$input?.on?.("keydown", (ev) => {
			if (ev.key === "Escape") {
				ev.preventDefault();
				ev.stopPropagation();
				this.stopEditing();
			} else if (ev.key === "ArrowDown" && ev.altKey) {
				ev.preventDefault();
				ev.stopPropagation();
				showNativeList(selectEl);
			}
		});
	}

	getGui() {
		return this.host;
	}

	afterGuiAttached() {
		if (this._abort) {
			this.params?.stopEditing?.(true);
			return;
		}
		if (this._needProject) {
			frappe.show_alert({
				message: __("Сначала выберите проект"),
				indicator: "orange",
			});
			const api = this.params?.api;
			const rowIndex = this.params?.node?.rowIndex;
			this.params?.stopEditing?.(true);
			scheduleStartEdit(api, rowIndex, FIELD_PROJECT);
			return;
		}
		if (this._empty) {
			frappe.show_alert({
				message: __("Нет доступных вариантов"),
				indicator: "orange",
			});
			this.params?.stopEditing?.(true);
			return;
		}
		/* Defer picker: same-tick mount + showPicker can blur-close (core focus). */
		setTimeout(() => {
			if (this._stopped) {
				return;
			}
			showNativeList(this._selectEl);
		}, 0);
	}

	focusIn() {
		this._selectEl?.focus?.({ preventScroll: true });
	}

	getValue() {
		return this.params?.value;
	}

	isCancelAfterEnd() {
		return true;
	}

	stopEditing() {
		if (this._stopped) {
			return;
		}
		this._stopped = true;
		const api = this.params?.api;
		const rowIndex = this.params?.node?.rowIndex;
		const nextField = this._nextField;
		this.params?.stopEditing?.(true);
		if (nextField) {
			scheduleStartEdit(api, rowIndex, nextField);
		}
	}

	destroy() {
		this._control = null;
		this._selectEl = null;
		this.host = null;
		this.params = null;
		this.frm = null;
	}
}

/** Second click (click-when-active) → core startEditingCell. */
export function onCascadeActiveClickEdit(event) {
	const field = event?.colDef?.field || event?.column?.getColId?.();
	const rowIndex = event?.node?.rowIndex;
	if (rowIndex == null || !CASCADE_FIELDS.includes(field)) {
		return;
	}
	event.api?.startEditingCell?.({ rowIndex, colKey: field });
}

/**
 * Programmatic open (add-row, post-commit). `openList: false` = focus only.
 * @param {{
 *   frm: object,
 *   params: object,
 *   field: string,
 *   openList?: boolean,
 *   deferActivate?: boolean,
 * }} opts
 */
export function openCascadeSelect(
	frm,
	{ params, field, openList = false, deferActivate = false }
) {
	if (!canEdit(frm) || !CASCADE_FIELDS.includes(field)) {
		return;
	}
	if (!ensureCatalog(frm)) {
		return;
	}
	const api = params?.api;
	const rowNode = params?.node;
	const row = params?.data || rowNode?.data;
	if (!api || !rowNode || row?.rowType !== "position") {
		return;
	}

	api.ensureColumnVisible?.(field);
	api.setFocusedCell?.(rowNode.rowIndex, field);
	if (!openList) {
		return;
	}
	const start = () => {
		api.startEditingCell?.({ rowIndex: rowNode.rowIndex, colKey: field });
	};
	if (deferActivate) {
		setTimeout(start, 0);
	} else {
		start();
	}
}
