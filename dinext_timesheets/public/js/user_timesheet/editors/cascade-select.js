/**
 * Inline Frappe Select: Project → Task → Role.
 * UI = custom select; data commit = DinextTable.commitCellChanges (undo/redo).
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

function queryCell(api, rowIndex, field) {
	const root =
		api?.getGridElement?.() ||
		document.querySelector(".user-timesheet-table");
	if (!root || rowIndex == null) {
		return null;
	}
	const col = typeof CSS !== "undefined" && CSS.escape ? CSS.escape(field) : field;
	return root.querySelector(`.ag-row[row-index="${rowIndex}"] .ag-cell[col-id="${col}"]`);
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

/** Build options + display + commit for one cascade field. */
function resolveField(frm, row, params, field) {
	if (field === FIELD_PROJECT) {
		const projects = projectOptionsForRow(frm, row);
		const mapped = buildProjectSelectOptions(projects);
		const current = mapped.find((m) => m.project.name === row.project);
		return {
			options: mapped.map((m) => m.option),
			displayValue: current?.option || row.project_label || "",
			onCommit: (next) => {
				const project = resolveProjectOption(projects, next);
				if (!project) {
					frappe.msgprint(__("Проект не найден"));
					refreshCells(params, [FIELD_PROJECT]);
					return;
				}
				const patch = buildProjectPatch(project);
				if (!commitCascadePatch(frm, params, patch)) {
					refreshCells(params, [FIELD_PROJECT, FIELD_TASK, FIELD_ROLE]);
					return;
				}
				openCascadeSelect(frm, {
					params,
					field: patch.document_name ? FIELD_ROLE : FIELD_TASK,
					openList: !patch.document_name || !patch.project_role,
				});
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
					return;
				}
				const patch = buildTaskPatch(frm, row, task);
				if (!commitCascadePatch(frm, params, patch)) {
					refreshCells(params, [FIELD_TASK, FIELD_ROLE]);
					return;
				}
				openCascadeSelect(frm, {
					params,
					field: FIELD_ROLE,
					openList: !(patch.project_role || row.project_role),
				});
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
		},
	};
}

function mountSelect(frm, wrap, row, params, field, { openList: shouldOpenList, deferActivate }) {
	if (wrap.querySelector(".ut-select-edit")) {
		return;
	}
	const spec = resolveField(frm, row, params, field);
	if (spec.needProject) {
		frappe.show_alert({
			message: __("Сначала выберите проект"),
			indicator: "orange",
		});
		openCascadeSelect(frm, { params, field: FIELD_PROJECT, openList: true });
		return;
	}
	if (!spec.options?.length) {
		frappe.show_alert({
			message: __("Нет доступных вариантов"),
			indicator: "orange",
		});
		return;
	}

	const oldValue = spec.displayValue || "";
	wrap.classList.add("ut-select-cell--editing");
	wrap.replaceChildren();
	const host = document.createElement("div");
	host.className = "ut-select-edit";
	wrap.appendChild(host);

	let finished = false;
	let blurArmed = !deferActivate;

	const finish = async (commit) => {
		if (finished) {
			return;
		}
		finished = true;
		const control = host._control;
		const next = control ? control.get_value() : oldValue;
		if (commit && next != null && String(next) !== String(oldValue)) {
			await spec.onCommit(String(next));
		} else {
			refreshCells(params, [field]);
		}
		host._control = null;
	};

	const control = frappe.ui.form.make_control({
		parent: $(host),
		only_input: true,
		df: {
			fieldname: field,
			fieldtype: "Select",
			label: "",
			options: spec.options.join("\n"),
		},
		render_input: true,
	});
	host._control = control;
	if (oldValue) {
		control.set_value(oldValue);
	}
	control.$wrapper?.addClass?.("ut-select-control");
	control.$wrapper?.find?.(".control-label, .help-box, .clearfix")?.hide?.();

	const selectEl = control.$input?.get?.(0);
	const activate = () => {
		if (finished) {
			return;
		}
		blurArmed = true;
		selectEl?.focus?.({ preventScroll: true });
		if (shouldOpenList) {
			showNativeList(selectEl);
		}
	};
	if (deferActivate) {
		setTimeout(activate, 0);
	} else {
		activate();
	}

	control.$input?.on?.("change", () => void finish(true));
	control.$input?.on?.("keydown", (ev) => {
		if (ev.key === "Escape") {
			ev.preventDefault();
			ev.stopPropagation();
			void finish(false);
		} else if (ev.key === "ArrowDown" && ev.altKey) {
			ev.preventDefault();
			ev.stopPropagation();
			showNativeList(selectEl);
		}
	});
	control.$input?.on?.("blur", () => {
		setTimeout(() => {
			if (blurArmed) {
				void finish(false);
			}
		}, 150);
	});
}

/**
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

	const tryMount = () => {
		const cell = queryCell(api, rowNode.rowIndex, field);
		const wrap = cell?.querySelector?.(".ut-select-cell");
		if (!wrap) {
			return false;
		}
		const liveRow = rowNode.data || row;
		mountSelect(frm, wrap, liveRow, { ...params, eGridCell: cell, data: liveRow, node: rowNode }, field, {
			openList,
			deferActivate,
		});
		return true;
	};

	if (!tryMount()) {
		requestAnimationFrame(() => tryMount());
	}
}

/** Enter / F2 / Space / Alt+↓ on focused cascade cell. */
export function handleCascadeCellKeyDown(frm, event) {
	const dom = event?.event;
	const key = dom?.key;
	const field = event.colDef?.field || event.column?.getColId?.();
	if (!key || !CASCADE_FIELDS.includes(field)) {
		return;
	}
	if (dom.target?.closest?.(".ut-select-edit")) {
		return;
	}
	if (
		key !== "Enter" &&
		key !== "F2" &&
		key !== " " &&
		!(key === "ArrowDown" && dom.altKey)
	) {
		return;
	}

	dom.preventDefault?.();
	dom.stopPropagation?.();
	openCascadeSelect(frm, { params: event, field, openList: true });
}
