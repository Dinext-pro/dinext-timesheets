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

/** Drop table + domain leftovers. Frappe reuses frm when New follows an open UT. */
export function resetTimesheetRuntime(frm) {
	if (!frm) {
		return;
	}
	destroyTable(frm);
	const field = frm.get_field?.("timesheet_details");
	field?.$wrapper?.empty();
	delete frm.ut;
	frm.ts_positions = [];
	frm.deletedPositions = [];
	frm.template_doc = null;
	frm.tasks_data = null;
	frm.ts_positions_with_active_tasks = null;
	frm.dates = [];
	frm.holidays = [];
	frm.work_hours = [];
	frm._ut_chrome_ready = null;
	frm._ut_chrome_inflight = false;
	frm._ut_dash_gen = 0;
	frm._ut_wf_gen = 0;
	frm._ut_wf_button_labels = [];
	document.body.classList.remove("ut-show-connections");
	frm.dashboard?.links_area?.hide?.();
}
