import { initState } from "./state.js";
import { loadGridData, reloadTable } from "./data.js";
import { getColumns } from "./columns.js";
import { canEdit } from "./model.js";
import { onSaveCells, onValidateCells } from "./save.js";
import { syncInvalidCellTooltip } from "./invalid-cells.js";
import {
	bindDescriptionPopoverGesture,
	closeDescriptionPopoverIfSuppressed,
	closeDescriptionPopoverOnScroll,
	handleDayDescrCellFocused,
	handleDayDescrCellMouseOut,
	handleDayDescrCellMouseOver,
	handleDayDescrKeyDown,
	syncDescriptionPopoverAfterGesture,
} from "./editors/description-popover.js";

import { showTaskPlanFact } from "./limits.js";
import { FIELD_PROJECT, FIELD_TASK } from "./editors/cascade-commit.js";
import {
	cancelPendingPicker,
	onPickerCellClicked,
} from "./editors/cascade-select.js";
import { closeTaskPicker, isTaskPickerOpen } from "./editors/task-picker-modal.js";
import { scheduleCascadeLayout } from "./column-layout.js";
import {
	applyToolbarChrome,
	canCheckTimesheetRow,
	onAddTimesheetRow,
	onDeleteTimesheetRows,
	onValidateDeleteTimesheetRows,
	syncRowsFromTable,
} from "./toolbar.js";
import {
	bindFillHandleFit,
	bindTimesheetTableFit,
	fitTimesheetTable,
	scheduleFitTimesheetTable,
} from "./fit.js";
import { attachRejectReasonRows } from "./rows.js";


const FS_SHELL_CLASS = "user-timesheet-shell--fullscreen";
const REJECT_ROW_H = 30;
const REJECT_HOVER_CLOSE_MS = 80;

function isRejectReasonRow(row) {
	return row?.rowType === "reject_reason";
}

function rejectHoverParent(frm) {
	return frm?.ut?._rejectHoverParent || "";
}

function setRejectHover(frm, parentId) {
	const next = parentId ? String(parentId) : "";
	if (!frm?.ut || rejectHoverParent(frm) === next) {
		return;
	}
	frm.ut._rejectHoverParent = next;
	const rows = attachRejectReasonRows(frm.ut.rows || [], next);
	frm.ut.rows = rows;
	if (frm.ut.table?.refresh) {
		frm.ut.table.refresh(rows);
	} else {
		frm.ut.table?.api?.resetRowHeights?.();
		frm.ut.table?.api?.redrawRows?.();
	}
	fitTimesheetTable(frm);
}

function rejectHoverIdFromRow(row) {
	if (row?.rowType === "reject_reason") {
		return row.parent_id || "";
	}
	if (row?.rowType === "position" && row.status === "Отклонено" && row.reject_reason) {
		return row.id;
	}
	return "";
}

function isRejectHoverDom(el) {
	const row = el?.closest?.(".ag-row");
	if (!row) {
		return false;
	}
	return (
		row.classList.contains("ut-rejected-row") ||
		row.classList.contains("ut-reject-reason-row")
	);
}

function handleRejectRowHover(frm, event) {
	const id = rejectHoverIdFromRow(event?.data);
	if (id) {
		if (frm.ut?._rejectHoverClose) {
			clearTimeout(frm.ut._rejectHoverClose);
			frm.ut._rejectHoverClose = null;
		}
		setRejectHover(frm, id);
		return;
	}
	handleRejectRowLeave(frm, event);
}

function handleRejectRowLeave(frm, event) {
	if (isRejectHoverDom(event?.event?.relatedTarget)) {
		return;
	}
	if (!frm.ut) {
		return;
	}
	clearTimeout(frm.ut._rejectHoverClose);
	frm.ut._rejectHoverClose = setTimeout(() => {
		frm.ut._rejectHoverClose = null;
		setRejectHover(frm, "");
	}, REJECT_HOVER_CLOSE_MS);
}

function syncReadonlyChrome(frm) {
	const el = frm?.ut?.container;
	if (!el) {
		return;
	}
	el.classList.toggle("ut-table--readonly", !canEdit(frm));
}

function bindReadonlyReorderBlock(frm, container) {
	if (!container || container._utReadonlyReorderBound) {
		return;
	}
	container.addEventListener(
		"mousedown",
		(event) => {
			if (canEdit(frm)) {
				return;
			}
			if (
				event.target.closest(
					".dinext-table-row-reorder-handle, .dinext-table-row-reorder-handle-host, .dinext-table-row-reorder-cell"
				)
			) {
				event.preventDefault();
				event.stopImmediatePropagation();
			}
		},
		true
	);
	container.addEventListener("mouseleave", () => setRejectHover(frm, ""));
	container._utReadonlyReorderBound = true;
}

function getTimesheetRowHeight(frm) {
	return function (params) {
		const row = params?.data;
		if (row?.rowType === "reject_reason") {
			return rejectHoverParent(frm) === String(row.parent_id) ? REJECT_ROW_H : 0;
		}
		return REJECT_ROW_H;
	};
}

function isFullWidthRejectRow(params) {
	return isRejectReasonRow(params?.rowNode?.data || params?.data);
}

function renderRejectReasonRow(params) {
	const el = document.createElement("div");
	el.className = "ut-reject-reason";
	el.textContent = params?.data?.reject_reason || "";
	return el;
}

function handleCheckedRowsDelete(frm, event) {
	const dom = event?.event;
	if (!dom || (dom.key !== "Delete" && dom.code !== "Delete")) {
		return false;
	}
	if (dom.altKey || dom.ctrlKey || dom.metaKey || dom.shiftKey) {
		return false;
	}
	const table = frm.ut?.table;
	const ids = table?.getCheckedRowIds?.() || [];
	if (!ids.length) {
		return false;
	}
	dom.preventDefault?.();
	dom.stopPropagation?.();
	void table.deleteCheckedRows();
	return true;
}

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
	cancelPendingPicker();
	if (isTaskPickerOpen()) {
		closeTaskPicker();
	}
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

function isTimesheetLeaveFenceRow(row) {
	return row?.rowType === "section" || row?.rowType === "leave";
}

/** Leave block is a suffix: no insert at/after first section/leave. */
function canAcceptTimesheetRowReorder({ dropTarget, sourceRows }) {
	if (!dropTarget || dropTarget.noop) {
		return true;
	}
	const fence = (sourceRows || []).findIndex(isTimesheetLeaveFenceRow);
	if (fence < 0) {
		return true;
	}
	return dropTarget.toIndex <= fence;
}

function getTimesheetRowClass(frm) {
	return function (params) {
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
		if (row.rowType === "reject_reason") {
			classes.push("ut-reject-reason-row");
			if (rejectHoverParent(frm) === String(row.parent_id)) {
				classes.push("ut-reject-reason-row--open");
			}
		}
		if (row.rowType === "position" && row.status === "Отклонено" && row.reject_reason) {
			classes.push("ut-rejected-row");
		}
		if (row.rowType === "position" && row.limit_status) {
			classes.push(`ut-limit-row-${row.limit_status}`);
		}
		return classes.join(" ");
	};
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
		canAcceptRowReorder: canAcceptTimesheetRowReorder,
		onRowReorder: () => syncRowsFromTable(frm),
		rowCheck: {
			enabled: editable,
			unit: "row",
			selectAll: true,
			checkNewRow: false,
			width: 26,
		},
		filter: { enabled: false },
		toolbar: {
			enabled: editable,
			defaultPinned: true,
			lockPinned: true,
			persistKey: `user-timesheet:${frm.doc?.name || "new"}`,
			presets: editable ? ["history", "rows"] : [],
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
			enableBrowserTooltips: true,
			tooltipShowDelay: 300,
			getRowClass: getTimesheetRowClass(frm),
			getRowHeight: getTimesheetRowHeight(frm),
			isFullWidthRow: isFullWidthRejectRow,
			fullWidthCellRenderer: renderRejectReasonRow,
			/* Domain callbacks chain with selection/clipboard/fillHandle (mergeGridOptions). */
			onCellClicked: (event) => onPickerCellClicked(frm, event),
			onCellKeyDown: (event) => {
				if (handleCheckedRowsDelete(frm, event)) {
					return false;
				}
				handleDayDescrKeyDown(frm, event);
				/* Selection mixin runs after this handler (Ctrl+A / Shift+arrows). */
				setTimeout(() => closeDescriptionPopoverIfSuppressed(frm), 0);
			},
			/* demodev hours focus → companion; covers mouse + keyboard (no separate onCellClicked). */
			onCellFocused: (event) => handleDayDescrCellFocused(frm, event),
			onCellMouseOver: (event) => {
				handleRejectRowHover(frm, event);
				handleDayDescrCellMouseOver(frm, event);
				syncInvalidCellTooltip(frm, event);
			},
			onCellMouseOut: (event) => {
				handleRejectRowLeave(frm, event);
				handleDayDescrCellMouseOut(frm, event);
			},
			onBodyScroll: () => closeDescriptionPopoverOnScroll(),
			onGridSizeChanged: () => {
				if (frm.ut?._addingRow || isTaskPickerOpen()) {
					return;
				}
				scheduleCascadeLayout(frm);
				if (frm.ut?.container?.classList.contains("ut-table--hug")) {
					return;
				}
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
			bindReadonlyReorderBlock(frm, state.container);
			syncReadonlyChrome(frm);
			const table = await DinextTable.create(buildTableOptions(frm, state));
			state.table = table;
			bindFillHandleFit(frm, table);
			bindDescriptionPopoverGesture(frm, table);
			bindTimesheetTableFit(frm);
			requestAnimationFrame(() => {
				scheduleCascadeLayout(frm);
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
	syncReadonlyChrome(frm);
	state.table.setSummaryRows?.(state.summaryRows || []);
	state.table.refresh?.(state.rows);
	scheduleCascadeLayout(frm);
	scheduleFitTimesheetTable(frm);
}

export { reloadTable };
