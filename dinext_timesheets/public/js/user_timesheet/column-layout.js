/**
 * Pinned Project / Task / Role widths: free space × 40/40/20, floors at minWidth.
 * AG Grid ignores flex on pinned cols — explicit widths instead.
 */
import { canEdit } from "./model.js";
import { FIELD_PROJECT, FIELD_ROLE, FIELD_TASK } from "./editors/cascade-commit.js";
import { isTaskPickerOpen } from "./editors/task-picker-modal.js";

const DAY_W = 54;
const LIMIT_W = 30;
const TOTAL_W = 72;
const ROW_CHECK_W = 26;
const ROW_REORDER_W = 22;
/* Native scrollbar is 11px here; extra pixels absorb AG fractional rounding. */
const VERTICAL_SCROLL_W = 14;

const CASCADE = [
	{ field: FIELD_PROJECT, ratio: 0.4, minWidth: 130 },
	{ field: FIELD_TASK, ratio: 0.4, minWidth: 150 },
	{ field: FIELD_ROLE, ratio: 0.2, minWidth: 110 },
];

function fixedColumnsWidth(frm) {
	const dates = frm.ut?.dates || [];
	let fixed =
		LIMIT_W +
		TOTAL_W +
		ROW_REORDER_W +
		VERTICAL_SCROLL_W +
		DAY_W * dates.length;
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

/** Measure grid, subtract fixed cols, set pinned cascade widths. */
export function layoutCascadeColumns(frm) {
	if (frm.ut?._addingRow || isTaskPickerOpen()) {
		return;
	}
	const api = frm.ut?.table?.api;
	if (!api) {
		return;
	}
	const viewport = gridViewportWidth(frm, api);
	if (viewport < 80) {
		return;
	}
	const free = viewport - fixedColumnsWidth(frm);
	const widths = distributeCascadeWidths(free);
	applyWidths(api, widths);
	remember(frm, widths);
}

export function getCascadeColDefWidth(field) {
	const c = CASCADE.find((x) => x.field === field);
	return c?.minWidth || 120;
}

export { CASCADE as CASCADE_LAYOUT };
