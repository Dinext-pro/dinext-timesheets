/**
 * Pinned Project / Task / Role widths: free space × 40/40/20, floors at minWidth.
 * AG Grid ignores flex on pinned cols — explicit widths instead.
 */
import { canEdit } from "./model.js";
import { FIELD_PROJECT, FIELD_ROLE, FIELD_TASK } from "./editors/cascade-select.js";

const DAY_W = 54;
const LIMIT_W = 30;
const TOTAL_W = 72;
const ROW_CHECK_W = 36;
/** Reserve for AG vertical scrollbar / chrome — first guess stays under. */
const CHROME_PAD = 16;

const CASCADE = [
	{ field: FIELD_PROJECT, ratio: 0.4, minWidth: 140 },
	{ field: FIELD_TASK, ratio: 0.4, minWidth: 160 },
	{ field: FIELD_ROLE, ratio: 0.2, minWidth: 120 },
];

function fixedColumnsWidth(frm) {
	const dates = frm.ut?.dates || [];
	let fixed = LIMIT_W + TOTAL_W + DAY_W * dates.length;
	if (canEdit(frm)) {
		fixed += ROW_CHECK_W;
	}
	return fixed;
}

/** free × ratios, then raise to mins; if overflow, shrink above-min. Remainder → Task. */
export function distributeCascadeWidths(freePx) {
	const free = Math.max(0, Math.floor(freePx));
	const widths = CASCADE.map((c) => Math.max(c.minWidth, free * c.ratio));
	let overflow = widths.reduce((a, b) => a + b, 0) - free;

	while (overflow > 0.5) {
		const shrinkable = [];
		for (let i = 0; i < widths.length; i++) {
			const slack = widths[i] - CASCADE[i].minWidth;
			if (slack > 0.5) {
				shrinkable.push(i);
			}
		}
		if (!shrinkable.length) {
			break;
		}
		const share = overflow / shrinkable.length;
		for (const i of shrinkable) {
			const slack = widths[i] - CASCADE[i].minWidth;
			const take = Math.min(slack, share);
			widths[i] -= take;
			overflow -= take;
		}
	}

	const ints = widths.map((w) => Math.max(1, Math.floor(w)));
	const used = ints.reduce((a, b) => a + b, 0);
	const rem = free - used;
	if (rem > 0) {
		ints[1] += rem;
	}
	return ints;
}

function gridRoot(api, frm) {
	return (
		api?.getGridElement?.() ||
		api?.getGui?.() ||
		frm?.ut?.container ||
		document.querySelector(".user-timesheet-table")
	);
}

function gridViewportWidth(frm, api) {
	return gridRoot(api, frm)?.clientWidth || 0;
}

/**
 * Real horizontal overflow (px). Sum(cols) vs clientWidth lies when v-scrollbar
 * steals space from the column band.
 */
function measureHOverflow(api, frm) {
	const root = gridRoot(api, frm);
	if (!root) {
		return 0;
	}
	const scroll = root.querySelector(".ag-body-horizontal-scroll-viewport");
	if (scroll && scroll.scrollWidth > 0) {
		return Math.max(0, scroll.scrollWidth - scroll.clientWidth);
	}
	const center = root.querySelector(".ag-center-cols-viewport");
	if (center) {
		return Math.max(0, center.scrollWidth - center.clientWidth);
	}
	return 0;
}

function applyWidths(api, widths) {
	const entries = CASCADE.map((c, i) => ({
		key: c.field,
		newWidth: widths[i],
	}));
	if (typeof api.setColumnWidths === "function") {
		api.setColumnWidths(entries, false);
		return;
	}
	if (typeof api.applyColumnState === "function") {
		api.applyColumnState({
			state: entries.map((e) => ({ colId: e.key, width: e.newWidth })),
		});
		return;
	}
	for (const e of entries) {
		api.setColumnWidth?.(e.key, e.newWidth);
	}
}

function remember(frm, widths) {
	if (frm.ut) {
		frm.ut._cascadeColWidths = Object.fromEntries(
			CASCADE.map((c, i) => [c.field, widths[i]])
		);
	}
}

function shrinkBy(widths, px) {
	const next = widths.slice();
	let left = Math.ceil(px);
	for (const i of [1, 0, 2]) {
		if (left <= 0) {
			break;
		}
		const can = next[i] - CASCADE[i].minWidth;
		if (can <= 0) {
			continue;
		}
		const take = Math.min(can, left);
		next[i] -= take;
		left -= take;
	}
	return next;
}

/** Fill empty center before pinned «Итого» (underfill only). */
function absorbCenterSlack(frm, api, widths) {
	const root = gridRoot(api, frm);
	const center = root?.querySelector?.(".ag-center-cols-viewport");
	if (!center) {
		return widths;
	}
	const daysW = DAY_W * (frm.ut?.dates?.length || 0);
	const slack = Math.floor(center.clientWidth - daysW);
	if (slack <= 2) {
		return widths;
	}
	const next = widths.slice();
	next[1] += slack;
	applyWidths(api, next);
	return next;
}

/** Shrink until horizontal scroll is gone (measure real overflow). */
function fitNoHScroll(frm, api, widths) {
	let next = widths;
	for (let i = 0; i < 8; i++) {
		const over = measureHOverflow(api, frm);
		if (over <= 0) {
			break;
		}
		next = shrinkBy(next, over);
		applyWidths(api, next);
	}
	return next;
}

/** Measure grid, subtract fixed cols, set pinned cascade widths. */
export function layoutCascadeColumns(frm) {
	const api = frm.ut?.table?.api;
	if (!api) {
		return;
	}
	const viewport = gridViewportWidth(frm, api);
	if (viewport < 80) {
		return;
	}
	/* First guess under — chrome pad avoids immediate h-scroll. */
	const free = viewport - fixedColumnsWidth(frm) - CHROME_PAD;
	let widths = distributeCascadeWidths(free);
	applyWidths(api, widths);

	requestAnimationFrame(() => {
		widths = absorbCenterSlack(frm, api, widths);
		requestAnimationFrame(() => {
			widths = fitNoHScroll(frm, api, widths);
			remember(frm, widths);
		});
	});
	remember(frm, widths);
}

export function getCascadeColDefWidth(field) {
	const c = CASCADE.find((x) => x.field === field);
	return c?.minWidth || 120;
}

export { CASCADE as CASCADE_LAYOUT };
