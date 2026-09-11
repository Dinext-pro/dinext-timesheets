import { closeDescriptionPopover } from "./editors/description-popover.js";
import { unbindTimesheetTableFit } from "./fit.js";

/**
 * Table runtime state on frm.ut (WE uses frm.we).
 * Position model for limits/copy CS compat: frm.ts_positions.
 */
export function initState(frm) {
	if (!frm.ut) {
		frm.ut = {
			table: null,
			rows: [],
			summaryRows: [],
			columns: [],
			dates: [],
			holidays: [],
			leaves: [],
			workHours: [],
			tasksData: null,
			container: null,
			shell: null,
			invalidCells: new Set(),
			_mountPromise: null,
			_initPromise: null,
			_newRowSeq: 0,
		};
	}
	if (!(frm.ut.invalidCells instanceof Set)) {
		frm.ut.invalidCells = new Set();
	}
	if (!Array.isArray(frm.ts_positions)) {
		frm.ts_positions = [];
	}
	if (!Array.isArray(frm.deletedPositions)) {
		frm.deletedPositions = [];
	}
	return frm.ut;
}

export function getState(frm) {
	return frm?.ut || null;
}

export function destroyTable(frm) {
	const state = getState(frm);
	if (!state) {
		return;
	}
	closeDescriptionPopover();
	unbindTimesheetTableFit(frm);
	if (state.table?.destroy) {
		state.table.destroy();
	}
	state.table = null;
	state.container = null;
	state._mountPromise = null;
	state._initPromise = null;
}
