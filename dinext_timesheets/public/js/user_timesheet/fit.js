/**
 * Table height: hug content when few rows; else fill to viewport bottom.
 * Measure live toolbar/header/summary; grow before add so AG does not flash overflow.
 */
import { isCascadeSelectOpen } from "./editors/cascade-select.js";

const ROW_H = 30;
const HEADER_H = 30;
const GRID_BORDER_H = 2;
const BOTTOM_GAP = 12;
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
	const viewport =
		tableEl.querySelector(".ag-center-cols-viewport") ||
		tableEl.querySelector(".ag-body-viewport");
	if (!viewport || viewport.scrollWidth <= viewport.clientWidth + 1) {
		return 0;
	}
	const bar = tableEl.querySelector(".ag-body-horizontal-scroll");
	if (bar && bar.offsetHeight > 0 && bar.offsetParent !== null) {
		return bar.offsetHeight;
	}
	return 15;
}

function contentHeight(frm, tableEl) {
	const toolbar = tableEl.querySelector(".dinext-table-toolbar");
	const header = tableEl.querySelector(".ag-header");
	const floating = tableEl.querySelector(".ag-floating-bottom");
	const toolbarH = measureH(toolbar, 0);
	const headerH = measureH(header, HEADER_H);
	const nRows = (frm.ut?.rows || []).length;
	const nSummary = Math.max(1, (frm.ut?.summaryRows || []).length);
	const summaryH = floating
		? measureH(floating, nSummary * ROW_H)
		: nSummary * ROW_H;
	return (
		toolbarH +
		headerH +
		nRows * ROW_H +
		summaryH +
		horizontalScrollH(tableEl) +
		GRID_BORDER_H
	);
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

	/* Skip while cascade <select> is open — height swap can close the picker.
	   Add-row calls fit once before opening the select. */
	if (!frm.ut?._addingRow && isCascadeSelectOpen()) {
		el.classList.remove(FITTING_CLASS);
		return;
	}

	el.classList.add(FITTING_CLASS);

	const nRows = (frm.ut?.rows || []).length;
	const contentH = contentHeight(frm, el);
	const chromeH = contentH - nRows * ROW_H;
	const remaining = remainingHeight(el);
	const height = Math.max(chromeH, Math.min(contentH, remaining));
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
	const onResize = () => scheduleFitTimesheetTable(frm);
	window.addEventListener("resize", onResize);
	window.addEventListener("load", onResize);
	const fonts = document.fonts;
	if (fonts?.ready?.then) {
		fonts.ready.then(() => scheduleFitTimesheetTable(frm));
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
}
