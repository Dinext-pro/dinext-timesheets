import { initState, resetTimesheetRuntime } from "./state.js";
import { initTable, reloadTable, refreshRuntime } from "./table.js";

/** HTML field — host for DinextTable (same pattern as WE/P&L custom_* fields). */
const FIELD = "timesheet_details";
const SHELL_CLASS = "user-timesheet-shell";
const TABLE_CLASS = "user-timesheet-table";

/**
 * @param {JQuery} $wrapper
 * @returns {{ shell: HTMLElement, container: HTMLElement } | null}
 */
function resolveShell($wrapper) {
	let $shell = $wrapper.find(`.${SHELL_CLASS}`).first();
	if (!$shell.length) {
		$shell = $(`
			<div class="${SHELL_CLASS}">
				<div class="${TABLE_CLASS}"></div>
			</div>
		`);
		$wrapper.empty().append($shell);
	} else if (!$shell.find(`.${TABLE_CLASS}`).length) {
		$shell.append(`<div class="${TABLE_CLASS}"></div>`);
	}

	const shell = $shell[0];
	const container = $shell.find(`.${TABLE_CLASS}`)[0];
	if (!shell || !container) {
		return null;
	}

	return { shell, container };
}

/** Mount DinextTable into HTML field. Skip new/unsaved docs (demodev parity). */
export async function ensureMounted(frm) {
	if (!frm) {
		return;
	}
	if (frm.is_new() || frm.doc?.__islocal) {
		resetTimesheetRuntime(frm);
		return;
	}

	const field = frm.get_field(FIELD);
	if (!field?.$wrapper?.length) {
		return;
	}

	let state = initState(frm);
	if (state._docname && state._docname !== frm.doc.name) {
		resetTimesheetRuntime(frm);
		state = initState(frm);
	}

	const parts = resolveShell(field.$wrapper);
	if (!parts) {
		return;
	}

	state._docname = frm.doc.name;
	state.shell = parts.shell;
	state.container = parts.container;

	if (state._mountPromise) {
		return state._mountPromise;
	}

	state._mountPromise = (async () => {
		try {
			if (state.table) {
				await reloadTable(frm, initTable, refreshRuntime);
			} else {
				await initTable(frm);
			}
		} finally {
			state._mountPromise = null;
		}
	})();

	return state._mountPromise;
}

export function destroy(frm) {
	resetTimesheetRuntime(frm);
}
