/**
 * Domain helpers for DinextTable rowCheck / toolbar rows preset.
 * UI chrome = core toolbar (not custom DOM).
 */
import { canEdit } from "./model.js";
import { buildRows, positionToRow } from "./rows.js";
import { buildSummaryRows } from "./summary.js";
import { getColumns } from "./columns.js";
import { layoutCascadeColumns } from "./column-layout.js";
import { scheduleRefreshLimits } from "./limits.js";
import { listProjects } from "./catalog.js";
import { syncStartButtonState } from "./submit.js";

function syncTableSource(frm, rows) {
	const table = frm.ut?.table;
	if (!table) {
		return;
	}
	table.sourceData = rows;
	if (table.options) {
		table.options.data = rows;
	}
	if (Array.isArray(table.rowData)) {
		table.rowData = rows;
	}
}

function syncSummary(frm) {
	const state = frm.ut;
	if (!state?.table) {
		return;
	}
	state.summaryRows = buildSummaryRows(frm);
	state.table.setSummaryRows?.(state.summaryRows);
}

/** Keep frm.ut.rows aligned with table.sourceData after core mutations. */
export function syncRowsFromTable(frm) {
	const state = frm.ut;
	const table = state?.table;
	if (!state || !table) {
		return;
	}
	const rows = Array.isArray(table.sourceData) ? table.sourceData : state.rows || [];
	state.rows = rows;
	syncTableSource(frm, rows);
	syncSummary(frm);
}

/** Move newly appended position before leave block (core addRow always appends). */
function moveRowBeforeLeaves(sourceData, rowId) {
	if (!Array.isArray(sourceData)) {
		return false;
	}
	const idx = sourceData.findIndex((r) => String(r?.id) === String(rowId));
	if (idx < 0) {
		return false;
	}
	const leaveIdx = sourceData.findIndex(
		(r) => r?.rowType === "section" || r?.rowType === "leave"
	);
	if (leaveIdx < 0 || idx < leaveIdx) {
		return false;
	}
	const [row] = sourceData.splice(idx, 1);
	const nextLeave = sourceData.findIndex(
		(r) => r?.rowType === "section" || r?.rowType === "leave"
	);
	sourceData.splice(nextLeave >= 0 ? nextLeave : sourceData.length, 0, row);
	return true;
}

function focusNewRowProject(frm, rowId) {
	requestAnimationFrame(() => {
		const api = frm.ut?.table?.api;
		if (!api) {
			return;
		}
		let targetNode = null;
		api.forEachNode?.((node) => {
			if (String(node?.data?.id) === String(rowId)) {
				targetNode = node;
			}
		});
		if (!targetNode) {
			return;
		}
		api.ensureIndexVisible?.(targetNode.rowIndex);
		api.setFocusedCell?.(targetNode.rowIndex, "project_label");
		const rowEl = document.querySelector(
			`.user-timesheet-table .ag-row[row-index="${targetNode.rowIndex}"]`
		);
		const cell =
			rowEl?.querySelector?.('.ag-cell[col-id="project_label"]') ||
			rowEl?.querySelector?.('[col-id="project_label"]');
		const target = cell?.querySelector?.(".ut-select-cell") || cell;
		target?.dispatchEvent?.(
			new MouseEvent("click", { bubbles: true, cancelable: true })
		);
	});
}

/** Rows + summary only — no columnDefs rebuild. */
export function refreshRows(frm) {
	const state = frm.ut;
	if (!state?.table) {
		return;
	}
	state.rows = buildRows(frm);
	syncTableSource(frm, state.rows);
	state.table.refresh?.(state.rows);
	syncSummary(frm);
}

/** Full rebuild incl. day columns (period / chrome change). */
export function refreshGrid(frm) {
	const state = frm.ut;
	if (!state?.table) {
		return;
	}
	state.columns = getColumns(frm);
	state.table.setOption?.("columns", state.columns);
	refreshRows(frm);
	requestAnimationFrame(() => layoutCascadeColumns(frm));
}

export function applyToolbarChrome(frm) {
	const table = frm.ut?.table;
	if (!table?.setOption) {
		return;
	}
	const editable = canEdit(frm);
	table.setOption("rowCheck", { enabled: editable, unit: "row", selectAll: true });
	table.setOption("toolbar", {
		enabled: true,
		defaultPinned: true,
		persistKey: `user-timesheet:${frm.doc?.name || "new"}`,
		presets: editable
			? ["history", "rows", "fullscreen"]
			: ["history", "fullscreen"],
	});
}

/** @returns {object|false} plain row for core insert */
export function onAddTimesheetRow(frm) {
	if (!canEdit(frm)) {
		return false;
	}
	if (!listProjects(frm).length) {
		frappe.msgprint(__("Список задач ещё не загружен"));
		return false;
	}

	const state = frm.ut;
	state._newRowSeq = (state._newRowSeq || 0) + 1;
	const id = `new_${state._newRowSeq}`;
	const position = {
		name: id,
		new: true,
		user: frm.doc.timesheet_from,
		project: "",
		project_label: "",
		document_type: "Task",
		document_name: "",
		document_label: "",
		project_role: "",
		details: [],
		status: "",
	};
	frm.ts_positions.push(position);
	const row = positionToRow(frm, position);

	queueMicrotask(() => {
		const table = frm.ut?.table;
		if (!table) {
			return;
		}
		if (moveRowBeforeLeaves(table.sourceData, id)) {
			table.refresh?.(table.sourceData);
		}
		syncRowsFromTable(frm);
		scheduleRefreshLimits(frm);
		frm.dirty();
		syncStartButtonState(frm);
		focusNewRowProject(frm, id);
	});

	return row;
}

export function onValidateDeleteTimesheetRows(frm, ctx) {
	if (!canEdit(frm)) {
		return false;
	}
	const bad = (ctx.rows || []).some((r) => r?.rowType && r.rowType !== "position");
	if (bad) {
		frappe.show_alert({
			message: __("Можно удалять только строки позиций"),
			indicator: "orange",
		});
		return false;
	}
	return true;
}

/** After core optimistic remove — sync domain model. */
export function onDeleteTimesheetRows(frm, ctx) {
	const ids = new Set((ctx.rowIds || []).map(String));
	for (const row of ctx.rows || []) {
		if (row?.rowType === "position" && !row.isNew) {
			frm.deletedPositions.push(row.id);
		}
	}
	frm.ts_positions = (frm.ts_positions || []).filter(
		(p) => !ids.has(String(p.name))
	);
	syncRowsFromTable(frm);
	scheduleRefreshLimits(frm);
	frm.dirty();
	syncStartButtonState(frm);
}

export function canCheckTimesheetRow(frm, ctx) {
	if (!canEdit(frm)) {
		return false;
	}
	return ctx?.row?.rowType === "position";
}
