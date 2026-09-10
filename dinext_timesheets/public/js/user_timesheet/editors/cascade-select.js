/** Project / Task single-click bridge. Double-click remains Form navigation. */
import { canEdit } from "../model.js";
import { PICKER_FIELDS } from "./cascade-commit.js";
import { openTaskPicker } from "./task-picker-modal.js";

const OPEN_DELAY_MS = 250;
let _activeClickTimer = null;

export function cancelPendingPicker() {
	if (_activeClickTimer) {
		clearTimeout(_activeClickTimer);
		_activeClickTimer = null;
	}
}

export function onPickerCellClicked(frm, event) {
	cancelPendingPicker();
	const field = event?.colDef?.field || event?.column?.getColId?.();
	const rowIndex = event?.node?.rowIndex;
	const row = event?.data || event?.node?.data;
	const domEvent = event?.event;
	if (
		!canEdit(frm) ||
		row?.rowType !== "position" ||
		rowIndex == null ||
		!PICKER_FIELDS.includes(field) ||
		domEvent?.detail > 1
	) {
		return;
	}
	_activeClickTimer = setTimeout(() => {
		_activeClickTimer = null;
		const focused = event.api?.getFocusedCell?.();
		const focusedField = focused?.column?.getColId?.();
		if (
			focused &&
			(focused.rowIndex !== rowIndex || focusedField !== field)
		) {
			return;
		}
		openTaskPicker(frm, {
			node: event.node,
			data: row,
			event,
			field,
			anchor: domEvent?.target?.closest?.(".ag-cell"),
		});
	}, OPEN_DELAY_MS);
}
