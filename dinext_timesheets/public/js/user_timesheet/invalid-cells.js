/**
 * Visual invalid marks for UT grid cells (save/submit validators).
 * State: frm.ut.invalidCells = Map("rowId::field" → message).
 * Paint: cellClassRules → .ut-cell--invalid (CSS inset border).
 * Hover: native title + tooltipValueGetter.
 */
import {
	FIELD_PROJECT,
	FIELD_ROLE,
	FIELD_TASK,
} from "./editors/cascade-commit.js";

export const SUMMARY_ROW_ID = "ut_day_totals";

function key(rowId, field) {
	return `${rowId}::${field}`;
}

function ensureMap(frm) {
	if (!frm.ut) {
		return null;
	}
	if (!(frm.ut.invalidCells instanceof Map)) {
		frm.ut.invalidCells = new Map();
	}
	return frm.ut.invalidCells;
}

export function isCellInvalid(frm, rowId, field) {
	if (rowId == null || !field) {
		return false;
	}
	return !!frm.ut?.invalidCells?.has?.(key(rowId, field));
}

export function getInvalidCellMessage(frm, rowId, field) {
	if (rowId == null || !field) {
		return "";
	}
	return frm.ut?.invalidCells?.get?.(key(rowId, field)) || "";
}

/** cellClassRules fragment for columns that can be invalid. */
export function invalidCellClassRules(frm) {
	return {
		"ut-cell--invalid": (params) => {
			const row = params?.data;
			if (!row) {
				return false;
			}
			if (row.rowType !== "position" && row.id !== SUMMARY_ROW_ID) {
				return false;
			}
			return isCellInvalid(frm, row.id, params.colDef?.field);
		},
	};
}

export function invalidCellTooltipGetter(frm) {
	return (params) => {
		const row = params?.data;
		if (!row) {
			return undefined;
		}
		return getInvalidCellMessage(frm, row.id, params.colDef?.field) || undefined;
	};
}

/** Native title — works on pinned summary even if AG tooltip module is off. */
export function syncInvalidCellTooltip(frm, event) {
	const el = event?.eGridCell;
	if (!el) {
		return;
	}
	const msg = getInvalidCellMessage(frm, event?.data?.id, event?.colDef?.field);
	if (msg) {
		el.setAttribute("title", msg);
	} else {
		el.removeAttribute("title");
	}
}

function refreshMarks(frm, columns) {
	const api = frm.ut?.table?.api;
	if (!api) {
		return;
	}
	const cols = columns?.length ? columns : undefined;
	api.refreshCells?.({
		columns: cols,
		force: true,
	});
	const pinned = api.getPinnedBottomRow?.(0);
	if (pinned) {
		api.refreshCells?.({
			rowNodes: [pinned],
			columns: cols,
			force: true,
		});
	}
}

/** Replace marks and repaint. */
export function setInvalidCells(frm, entries) {
	const map = ensureMap(frm);
	if (!map) {
		return;
	}
	map.clear();
	const cols = new Set();
	for (const entry of entries || []) {
		if (entry?.rowId == null || !entry.field) {
			continue;
		}
		map.set(key(entry.rowId, entry.field), entry.message || "");
		cols.add(entry.field);
	}
	refreshMarks(frm, [...cols]);
}

export function clearInvalidCells(frm) {
	const map = frm.ut?.invalidCells;
	if (!map?.size) {
		return;
	}
	map.clear();
	refreshMarks(frm);
}

/** Drop marks for fields on a row after successful edit. */
export function clearInvalidFields(frm, rowId, fields) {
	const map = frm.ut?.invalidCells;
	if (!map?.size || rowId == null || !fields?.length) {
		return;
	}
	let changed = false;
	const cols = [];
	for (const field of fields) {
		if (map.delete(key(rowId, field))) {
			changed = true;
			cols.push(field);
		}
	}
	if (changed) {
		refreshMarks(frm, cols);
	}
}

/**
 * Clear marks after the user enters a value.
 * Day-hour edits also drop the pinned Total mark for that day.
 */
export function clearInvalidAfterEdit(frm, rowId, field) {
	clearInvalidFields(frm, rowId, displayFieldsForChange(field));
	if (field?.startsWith("day_")) {
		clearInvalidFields(frm, SUMMARY_ROW_ID, [field]);
	}
}

/** Map committed grid fields → display fields that may carry marks. */
export function displayFieldsForChange(field) {
	if (field === "project" || field === FIELD_PROJECT) {
		return [FIELD_PROJECT];
	}
	if (
		field === "document_name" ||
		field === "document_type" ||
		field === FIELD_TASK
	) {
		return [FIELD_TASK];
	}
	if (field === FIELD_ROLE || field === "project_role") {
		return [FIELD_ROLE];
	}
	if (field?.startsWith("day_")) {
		/* Day edit also clears submit "no hours" mark on total. */
		return [field, "total"];
	}
	if (field === "total") {
		return ["total"];
	}
	return field ? [field] : [];
}
