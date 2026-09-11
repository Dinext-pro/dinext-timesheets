/**
 * Visual invalid marks for UT grid cells (save/submit validators).
 * State: frm.ut.invalidCells = Set("rowId::field").
 * Paint: cellClassRules → .ut-cell--invalid (CSS inset border).
 */
import {
	FIELD_PROJECT,
	FIELD_ROLE,
	FIELD_TASK,
} from "./editors/cascade-commit.js";

function key(rowId, field) {
	return `${rowId}::${field}`;
}

function ensureSet(frm) {
	if (!frm.ut) {
		return null;
	}
	if (!(frm.ut.invalidCells instanceof Set)) {
		frm.ut.invalidCells = new Set();
	}
	return frm.ut.invalidCells;
}

export function isCellInvalid(frm, rowId, field) {
	if (rowId == null || !field) {
		return false;
	}
	return !!frm.ut?.invalidCells?.has(key(rowId, field));
}

/** cellClassRules fragment for columns that can be invalid. */
export function invalidCellClassRules(frm) {
	return {
		"ut-cell--invalid": (params) => {
			const row = params?.data;
			if (!row || row.rowType !== "position") {
				return false;
			}
			return isCellInvalid(frm, row.id, params.colDef?.field);
		},
	};
}

function refreshMarks(frm, columns) {
	frm.ut?.table?.api?.refreshCells?.({
		columns: columns?.length ? columns : undefined,
		force: true,
	});
}

/** Replace marks and repaint. */
export function setInvalidCells(frm, entries) {
	const set = ensureSet(frm);
	if (!set) {
		return;
	}
	set.clear();
	const cols = new Set();
	for (const entry of entries || []) {
		if (entry?.rowId == null || !entry.field) {
			continue;
		}
		set.add(key(entry.rowId, entry.field));
		cols.add(entry.field);
	}
	refreshMarks(frm, [...cols]);
}

export function clearInvalidCells(frm) {
	const set = frm.ut?.invalidCells;
	if (!set?.size) {
		return;
	}
	set.clear();
	refreshMarks(frm);
}

/** Drop marks for fields on a row after successful edit. */
export function clearInvalidFields(frm, rowId, fields) {
	const set = frm.ut?.invalidCells;
	if (!set?.size || rowId == null || !fields?.length) {
		return;
	}
	let changed = false;
	const cols = [];
	for (const field of fields) {
		if (set.delete(key(rowId, field))) {
			changed = true;
			cols.push(field);
		}
	}
	if (changed) {
		refreshMarks(frm, cols);
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
