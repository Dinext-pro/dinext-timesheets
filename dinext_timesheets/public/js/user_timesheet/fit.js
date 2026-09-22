/**
 * Table height: hug content when few rows; else fill to viewport bottom.
 * Measure live toolbar/header/summary; grow before add so AG does not flash overflow.
 */
import { isTaskPickerOpen } from "./editors/task-picker-modal.js";
import { scheduleCascadeLayout } from "./column-layout.js";
import { canEdit } from "./model.js";

const ROW_H = 30;
const HEADER_H = 30;
const GRID_BORDER_H = 2;
const BOTTOM_GAP = 12;
const FILL_HANDLE_SLACK = 12;
const FS_CLASS = "user-timesheet-shell--fullscreen";
const FITTING_CLASS = "ut-table--fitting";
const HUG_CLASS = "ut-table--hug";

function measureH(el, fallback) {
	if (!el) {
		return fallback;
	}
	const h = el.getBoundingClientRect().height;
	return h > 0 ? h : fallback;
}

function horizontalScrollH(tableEl) {
	const bar = tableEl.querySelector(".ag-body-horizontal-scroll");
	if (bar && bar.offsetHeight > 0 && bar.offsetParent !== null) {
		return bar.offsetHeight;
	}
	const viewport =
		tableEl.querySelector(".ag-center-cols-viewport") ||
		tableEl.querySelector(".ag-body-viewport");
	if (viewport && viewport.scrollWidth > viewport.clientWidth + 1) {
		return 15;
	}
	return 0;
}

/** AG keeps hidden reject rows at 1px — count live container, not n*30. */
function measuredBodyRowsHeight(frm, tableEl) {
	let h = 0;
	for (const sel of [
		".ag-center-cols-container",
		".ag-pinned-left-cols-container",
		".ag-full-width-container",
	]) {
		const node = tableEl.querySelector(sel);
		if (!node) {
			continue;
		}
		h = Math.max(h, node.scrollHeight || 0, measureH(node, 0));
	}
	const visible = visibleBodyRowCount(frm) * ROW_H;
	if (!visible) {
		return 0;
	}
	return Math.max(h, visible);
}

function visibleBodyRowCount(frm) {
	const hover = frm?.ut?._rejectHoverParent || "";
	let n = 0;
	for (const row of frm?.ut?.rows || []) {
		if (row?.rowType === "reject_reason") {
			if (hover && hover === String(row.parent_id)) {
				n += 1;
			}
			continue;
		}
		n += 1;
	}
	return n;
}

function contentParts(frm, tableEl) {
	const toolbarH = measureH(tableEl.querySelector(".dinext-table-toolbar"), 0);
	const headerH = measureH(tableEl.querySelector(".ag-header"), HEADER_H);
	const nSummary = Math.max(1, (frm.ut?.summaryRows || []).length);
	const floating = tableEl.querySelector(".ag-floating-bottom");
	const summaryH = floating
		? measureH(floating, nSummary * ROW_H)
		: nSummary * ROW_H;
	const bodyH = measuredBodyRowsHeight(frm, tableEl);
	const slack = canEdit(frm) && hasActiveCellRange(frm) ? FILL_HANDLE_SLACK : 0;
	const chromeH =
		toolbarH +
		headerH +
		summaryH +
		horizontalScrollH(tableEl) +
		GRID_BORDER_H +
		slack;
	return { bodyH, chromeH, contentH: chromeH + bodyH };
}

function hasActiveCellRange(frm) {
	const table = frm?.ut?.table;
	const ranges =
		table?.getCellRanges?.() || table?.api?.getCellRanges?.() || [];
	return ranges.length > 0;
}

/** Grow slack only while a range is selected — idle hug stays flush to summary. */
export function bindFillHandleFit(frm, table) {
	const api = table?.api;
	if (!frm?.ut || !api || frm.ut._fillFitBound) {
		return;
	}
	const onRange = () => scheduleFitTimesheetTable(frm);
	for (const ev of ["rangeSelectionChanged", "cellSelectionChanged"]) {
		api.addEventListener?.(ev, onRange);
	}
	frm.ut._fillFitBound = onRange;
}

function remainingHeight(el) {
	return Math.floor(
		window.innerHeight - el.getBoundingClientRect().top - BOTTOM_GAP
	);
}

function applyFitOverflow(el, hugs) {
	el.classList.toggle(HUG_CLASS, hugs);
	el.style.overflowY = hugs ? "hidden" : "";
}

export function growTimesheetTableForNewRow(frm) {
	const el = frm?.ut?.container;
	if (!el) {
		return;
	}
	const remaining = remainingHeight(el);
	const current = parseFloat(el.style.height) || el.getBoundingClientRect().height;
	const next = Math.min(current + ROW_H, Math.max(remaining, current));
	el.classList.add(FITTING_CLASS);
	el.style.height = `${next}px`;
	el.style.maxHeight = `${Math.max(remaining, next)}px`;
}

export function fitTimesheetTable(frm) {
	const el = frm?.ut?.container;
	if (!el) {
		return;
	}
	const shell = frm.ut.shell || el.closest(".user-timesheet-shell");
	if (shell?.classList.contains(FS_CLASS)) {
		el.style.height = "";
		el.style.maxHeight = "";
		el.classList.remove(FITTING_CLASS, HUG_CLASS);
		el.style.overflowY = "";
		return;
	}

	/* Keep the anchored picker stable while it is open. */
	if (!frm.ut?._addingRow && isTaskPickerOpen()) {
		el.classList.remove(FITTING_CLASS);
		return;
	}

	el.classList.add(FITTING_CLASS);

	const remaining = remainingHeight(el);
	let { contentH, chromeH } = contentParts(frm, el);
	let height = Math.max(chromeH, Math.min(contentH, remaining));
	el.style.height = `${height}px`;
	el.style.maxHeight = `${Math.max(remaining, height)}px`;

	({ contentH, chromeH } = contentParts(frm, el));
	const vp = el.querySelector(".ag-body-viewport");
	const bodyNow = measuredBodyRowsHeight(frm, el);
	const vpH = measureH(vp, 0);
	const overflow = vpH > 0 ? Math.max(0, bodyNow - vpH) : 0;
	contentH += overflow;
	height = Math.max(chromeH, Math.min(contentH, remaining));
	const hugs = height >= contentH - 1;

	el.style.height = `${height}px`;
	el.style.maxHeight = `${Math.max(remaining, height)}px`;
	applyFitOverflow(el, hugs);

	requestAnimationFrame(() => {
		el.classList.remove(FITTING_CLASS);
	});
}

export function scheduleFitTimesheetTable(frm) {
	if (!frm?.ut) {
		return;
	}
	if (frm.ut._fitTimer) {
		clearTimeout(frm.ut._fitTimer);
	}
	frm.ut._fitTimer = setTimeout(() => {
		frm.ut._fitTimer = null;
		fitTimesheetTable(frm);
	}, 50);
}

export function bindTimesheetTableFit(frm) {
	if (!frm?.ut || frm.ut._fitResizeBound) {
		return;
	}
	const onResize = () => {
		scheduleFitTimesheetTable(frm);
		scheduleCascadeLayout(frm);
	};
	window.addEventListener("resize", onResize);
	window.addEventListener("load", onResize);
	const fonts = document.fonts;
	if (fonts?.ready?.then) {
		fonts.ready.then(() => {
			scheduleFitTimesheetTable(frm);
			scheduleCascadeLayout(frm);
		});
	}
	requestAnimationFrame(() => {
		requestAnimationFrame(() => fitTimesheetTable(frm));
	});
	frm.ut._fitResizeBound = onResize;
}

export function unbindTimesheetTableFit(frm) {
	if (!frm?.ut) {
		return;
	}
	if (frm.ut._fitResizeBound) {
		window.removeEventListener("resize", frm.ut._fitResizeBound);
		window.removeEventListener("load", frm.ut._fitResizeBound);
		frm.ut._fitResizeBound = null;
	}
	if (frm.ut._fitTimer) {
		clearTimeout(frm.ut._fitTimer);
		frm.ut._fitTimer = null;
	}
	if (frm.ut._fillFitBound) {
		const api = frm.ut.table?.api;
		for (const ev of ["rangeSelectionChanged", "cellSelectionChanged"]) {
			api?.removeEventListener?.(ev, frm.ut._fillFitBound);
		}
		frm.ut._fillFitBound = null;
	}
}
