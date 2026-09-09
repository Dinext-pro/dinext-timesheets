import { initState } from "./state.js";
import { loadGridData, reloadTable } from "./data.js";
import { getColumns } from "./columns.js";
import { canEdit } from "./model.js";
import { onSaveCells, onValidateCells } from "./save.js";
import {
	closeDescriptionPopoverOnScroll,
	handleDayDescrCellFocused,
	handleDayDescrKeyDown,
} from "./editors/description-popover.js";

import { showTaskPlanFact } from "./limits.js";
import {
	FIELD_PROJECT,
	FIELD_TASK,
	isCascadeSelectOpen,
} from "./editors/cascade-select.js";
import { layoutCascadeColumns } from "./column-layout.js";
import {
	applyToolbarChrome,
	canCheckTimesheetRow,
	onAddTimesheetRow,
	onDeleteTimesheetRows,
	onValidateDeleteTimesheetRows,
} from "./toolbar.js";
import { bindTimesheetTableFit, scheduleFitTimesheetTable } from "./fit.js";

let _layoutTimer = null;
function scheduleCascadeLayout(frm) {
	if (_layoutTimer) {
		clearTimeout(_layoutTimer);
	}
	_layoutTimer = setTimeout(() => {
		_layoutTimer = null;
		layoutCascadeColumns(frm);
	}, 50);
}

const FS_SHELL_CLASS = "user-timesheet-shell--fullscreen";

function resolveFullscreenOpts(container) {
	const shell = container?.closest?.(".user-timesheet-shell");
	if (!shell) {
		return null;
	}
	const afterLayout = () => {
		requestAnimationFrame(() => window.dispatchEvent(new Event("resize")));
	};
	return {
		target: "shell",
		shell,
		onEnter: ({ element }) => {
			element?.classList.add(FS_SHELL_CLASS);
			afterLayout();
		},
		onExit: ({ element }) => {
			element?.classList.remove(FS_SHELL_CLASS);
			afterLayout();
		},
	};
}

function onCellDoubleClicked(frm, params) {
	const row = params?.data;
	if (!row) {
		return;
	}
	if (row.rowType === "section") {
		return;
	}
	if (row.rowType === "leave" && row.document_name) {
		frappe.set_route("Form", "Application For Leave", row.document_name);
		return;
	}
	if (row.rowType !== "position") {
		return;
	}
	const field = params.colDef?.field || "";
	if (field === FIELD_PROJECT || field === "project") {
		if (row.project) {
			frappe.set_route("Form", "Project", row.project);
		}
		return;
	}
	if (field === FIELD_TASK || field === "document_name") {
		if (row.document_name) {
			frappe.set_route(
				"Form",
				row.document_type || "Task",
				row.document_name
			);
		}
		return;
	}
	if (field === "limit_icon") {
		const pos = (frm.ts_positions || []).find(
			(p) => String(p.name) === String(row.id)
		);
		showTaskPlanFact(frm, pos || row);
	}
}

function getRowClass(params) {
	const row = params?.data;
	if (!row) {
		return "";
	}
	const classes = [];
	if (row.rowType === "section") {
		classes.push("ut-section-row");
	}
	if (row.rowType === "leave") {
		classes.push("ut-leave-row");
	}
	if (row.status === "Отклонено" && row.reject_reason) {
		classes.push("ut-rejected-row");
	}
	if (row.rowType === "position" && row.limit_status) {
		classes.push(`ut-limit-row-${row.limit_status}`);
	}
	return classes.join(" ");
}

function buildTableOptions(frm, state) {
	const editable = canEdit(frm);
	const opts = {
		container: state.container,
		data: state.rows,
		columns: state.columns,
		summaryRows: state.summaryRows || [],
		summary: { pin: "bottom", edit: false, clipboard: false, selection: false },
		edit: editable,
		selection: { enabled: true },
		clipboard: { enabled: editable },
		fillHandle: { enabled: editable },
		rowReorder: { enabled: true, width: 22 },
		canReorderRow: (ctx) => ctx?.row?.rowType === "position",
		rowCheck: {
			enabled: editable,
			unit: "row",
			selectAll: true,
			checkNewRow: false,
			width: 26,
		},
		filter: { enabled: false },
		toolbar: {
			enabled: true,
			defaultPinned: true,
			lockPinned: true,
			persistKey: `user-timesheet:${frm.doc?.name || "new"}`,
			presets: editable ? ["history", "rows"] : ["history"],
		},
		navigation: {
			enabled: editable,
			enterMovesDown: false,
			skipNonEditable: true,
			isRowNavigable: (row) => row?.rowType === "position",
		},
		theme: {
			cellHorizontalPadding: 6,
			columnBorder: true,
			headerColumnBorder: true,
		},
		canCheckRow: (ctx) => canCheckTimesheetRow(frm, ctx),
		onAddRow: () => onAddTimesheetRow(frm),
		onValidateDeleteRows: (ctx) => onValidateDeleteTimesheetRows(frm, ctx),
		onDeleteRows: (ctx) => onDeleteTimesheetRows(frm, ctx),
		onValidateCells: (ctx) => onValidateCells(frm, ctx),
		onSaveCells: (ctx) => onSaveCells(frm, ctx),
		/* Top-level: only onReady / onCellDoubleClicked are first-class in DinextTable. */
		onCellDoubleClicked: (params) => onCellDoubleClicked(frm, params),
		gridOptions: {
			rowHeight: 30,
			headerHeight: 30,
			/* Summary always pinned — empty body should not show "no rows" overlay. */
			suppressNoRowsOverlay: true,
			suppressMovableColumns: true,
			getRowClass,
			/* Domain callbacks chain with selection/clipboard/fillHandle (mergeGridOptions). */
			onCellKeyDown: (event) => {
				handleDayDescrKeyDown(frm, event);
			},
			/* demodev hours focus → companion; covers mouse + keyboard (no separate onCellClicked). */
			onCellFocused: (event) => handleDayDescrCellFocused(frm, event),
			onBodyScroll: () => closeDescriptionPopoverOnScroll(),
			onGridSizeChanged: () => {
				if (frm.ut?._addingRow || isCascadeSelectOpen()) {
					return;
				}
				scheduleCascadeLayout(frm);
				scheduleFitTimesheetTable(frm);
			},
		},
	};

	const fullscreen = resolveFullscreenOpts(state.container);
	if (fullscreen) {
		opts.fullscreen = fullscreen;
	}
	return opts;
}

export async function initTable(frm) {
	const state = initState(frm);
	if (!state.container) {
		return null;
	}
	if (state.table) {
		return state.table;
	}
	if (state._initPromise) {
		return state._initPromise;
	}

	state._initPromise = (async () => {
		try {
			await frappe.require([
				"dinext-table.bundle.js",
				"/assets/dinext_timesheets/css/user-timesheet.css",
			]);
			if (typeof DinextTable.load === "function") {
				await DinextTable.load();
			}
			await loadGridData(frm);
			state.columns = getColumns(frm);
			const table = await DinextTable.create(buildTableOptions(frm, state));
			state.table = table;
			bindTimesheetTableFit(frm);
			requestAnimationFrame(() => {
				layoutCascadeColumns(frm);
				scheduleFitTimesheetTable(frm);
			});
			return table;
		} finally {
			state._initPromise = null;
		}
	})();

	return state._initPromise;
}

export async function refreshRuntime(frm) {
	const state = frm.ut;
	if (!state?.table) {
		return;
	}
	const editable = canEdit(frm);
	state.columns = getColumns(frm);
	state.table.setOption?.("columns", state.columns);
	state.table.setOption?.("edit", editable);
	state.table.setOption?.("clipboard", { enabled: editable });
	state.table.setOption?.("fillHandle", { enabled: editable });
	state.table.setOption?.("navigation", {
		enabled: editable,
		enterMovesDown: false,
		skipNonEditable: true,
		isRowNavigable: (row) => row?.rowType === "position",
	});
	applyToolbarChrome(frm);
	state.table.setSummaryRows?.(state.summaryRows || []);
	state.table.refresh?.(state.rows);
	scheduleCascadeLayout(frm);
	scheduleFitTimesheetTable(frm);
}

export { reloadTable };
