/**
 * Domain helpers for DinextTable rowCheck / toolbar rows preset.
 * UI chrome = core toolbar (not custom DOM).
 */
import { canEdit } from "./model.js";
import { attachRejectReasonRows, buildRows, positionToRow } from "./rows.js";
import { buildSummaryRows } from "./summary.js";
import { getColumns } from "./columns.js";
import { layoutCascadeColumns } from "./column-layout.js";
import { scheduleRefreshLimits } from "./limits.js";
import { listProjects } from "./catalog.js";
import { syncStartButtonState } from "./submit.js";
import { fitTimesheetTable, growTimesheetTableForNewRow, scheduleFitTimesheetTable } from "./fit.js";
import { FIELD_PROJECT } from "./editors/cascade-commit.js";
import { openTaskPicker } from "./editors/task-picker-modal.js";

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
	const raw = Array.isArray(table.sourceData) ? table.sourceData : state.rows || [];
	const rows = attachRejectReasonRows(raw, state._rejectHoverParent);
	const changed = rows.length !== raw.length || rows.some((row, i) => row !== raw[i]);
	state.rows = rows;
	syncTableSource(frm, rows);
	if (changed) {
		state.table.refresh?.(rows);
	}
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

function insertIndexBeforeLeaves(sourceData) {
	const leaveIdx = sourceData.findIndex(
		(r) => r?.rowType === "section" || r?.rowType === "leave"
	);
	return leaveIdx >= 0 ? leaveIdx : sourceData.length;
}

/**
 * Insert one row via AG applyTransaction. Returning a row from onAddRow lets
 * core addRow call syncRowCheckGrid → setGridOption("rowData", [...]) and
 * remount every cell. Abort core by returning false after this.
 */
function spliceTimesheetRow(table, row, idx) {
	const source = table.sourceData;
	source.splice(idx, 0, row);
	if (table.options) {
		table.options.data = source;
	}
	if (Array.isArray(table.rowData)) {
		table.rowData = source;
	}
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
		if (!targetNode || targetNode.rowIndex == null) {
			return;
		}
		api.ensureIndexVisible?.(targetNode.rowIndex, "middle");
		api.ensureColumnVisible?.(FIELD_PROJECT);
		api.setFocusedCell?.(targetNode.rowIndex, FIELD_PROJECT);
		api.clearRangeSelection?.();
		api.addCellRange?.({
			rowStartIndex: targetNode.rowIndex,
			rowEndIndex: targetNode.rowIndex,
			columnStart: FIELD_PROJECT,
			columnEnd: FIELD_PROJECT,
		});
		const cellEl =
			api.getCellRendererInstances?.({
				rowNodes: [targetNode],
				columns: [FIELD_PROJECT],
			})?.[0]?.eGui?.closest?.(".ag-cell") ||
			frm.ut?.container?.querySelector?.(
				`.ag-row[row-index="${targetNode.rowIndex}"] .ag-cell[col-id="${FIELD_PROJECT}"]`
			);
		openTaskPicker(frm, {
			node: targetNode,
			data: targetNode.data,
			field: FIELD_PROJECT,
			anchor: cellEl || frm.ut?.container,
		});
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
	scheduleFitTimesheetTable(frm);
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
	table.setOption("rowCheck", {
		enabled: editable,
		unit: "row",
		selectAll: true,
		checkNewRow: false,
		width: 26,
	});
	table.setOption("filter", { enabled: false });
	table.setOption("toolbar", {
		enabled: editable,
		defaultPinned: true,
		lockPinned: true,
		persistKey: `user-timesheet:${frm.doc?.name || "new"}`,
		presets: editable ? ["history", "rows"] : [],
	});
}

/** @returns {object|false} plain row for core insert */
export function onAddTimesheetRow(frm) {
	if (!canEdit(frm)) {
		return false;
	}
	if (!listProjects(frm).length) {
		frappe.msgprint(__("Task list is not loaded yet"));
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
	const table = state.table;
	const source = table?.sourceData;
	if (table?.api?.applyTransaction && Array.isArray(source)) {
		const beforeBody = source.slice();
		const beforeChecked = table.getCheckedRowIds?.() || [];
		const idx = insertIndexBeforeLeaves(source);
		state._addingRow = true;
		spliceTimesheetRow(table, row, idx);
		state.rows = source;
		syncTableSource(frm, source);
		fitTimesheetTable(frm);
		table.api.applyTransaction({
			add: [row],
			addIndex: idx,
		});
		table.recordRowCheckUndo?.({
			beforeBody,
			afterBody: source.slice(),
			beforeSummary: null,
			afterSummary: null,
			beforeChecked,
			afterChecked: beforeChecked,
			syncSummary: false,
		});
		frm.dirty();
		syncStartButtonState(frm);
		focusNewRowProject(frm, id);
		requestAnimationFrame(() => {
			if (frm.ut) {
				frm.ut._addingRow = false;
			}
		});
		return false;
	}

	/* Fallback: core addRow appends + full rowData replace (blinks). */
	state._addingRow = true;
	growTimesheetTableForNewRow(frm);
	requestAnimationFrame(() => {
		requestAnimationFrame(() => afterAddTimesheetRow(frm, id));
	});
	return row;
}

function afterAddTimesheetRow(frm, id) {
	const table = frm.ut?.table;
	if (!table) {
		if (frm.ut) {
			frm.ut._addingRow = false;
		}
		return;
	}
	if (moveRowBeforeLeaves(table.sourceData, id) && table.api?.applyTransaction) {
		const idx = table.sourceData.findIndex((r) => String(r?.id) === String(id));
		const row = idx >= 0 ? table.sourceData[idx] : null;
		if (row) {
			table.api.applyTransaction({
				remove: [row],
				add: [row],
				addIndex: idx,
			});
			syncTableSource(frm, table.sourceData);
		}
	}
	if (table.toggleRowCheck) {
		table.toggleRowCheck(id, false);
	} else if (table.setCheckedRowIds && table.getCheckedRowIds) {
		table.setCheckedRowIds(
			table.getCheckedRowIds().filter((x) => String(x) !== String(id))
		);
	}
	const rows = Array.isArray(table.sourceData) ? table.sourceData : frm.ut.rows || [];
	frm.ut.rows = rows;
	syncTableSource(frm, rows);
	fitTimesheetTable(frm);
	frm.dirty();
	syncStartButtonState(frm);
	focusNewRowProject(frm, id);
	requestAnimationFrame(() => {
		if (frm.ut) {
			frm.ut._addingRow = false;
		}
	});
}

export function onValidateDeleteTimesheetRows(frm, ctx) {
	if (!canEdit(frm)) {
		return false;
	}
	const bad = (ctx.rows || []).some((r) => r?.rowType && r.rowType !== "position");
	if (bad) {
		frappe.show_alert({
			message: __("Only position rows can be deleted"),
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
	scheduleFitTimesheetTable(frm);
	frm.dirty();
	syncStartButtonState(frm);
}

export function canCheckTimesheetRow(frm, ctx) {
	if (!canEdit(frm)) {
		return false;
	}
	return ctx?.row?.rowType === "position";
}
