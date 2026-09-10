/**
 * Project / Task: core click-when-active → picker.
 * Role: in-cell Select (not this module).
 */
import { canEdit } from "../model.js";
import { PICKER_FIELDS } from "./cascade-commit.js";
import { openTaskPicker } from "./task-picker-modal.js";

let _activeClickTimer = null;

/** Drop pending open so dblclick can route to Form. */
export function cancelPendingPicker() {
	if (_activeClickTimer) {
		clearTimeout(_activeClickTimer);
		_activeClickTimer = null;
	}
}

/** AG editor that never mounts — Enter / F2 / active click open the picker. */
export class PickerCellEditor {
	init(params) {
		this.params = params;
	}

	isCancelBeforeStart() {
		const frm = this.params?.colDef?.cellEditorParams?.frm;
		if (!frm || !canEdit(frm)) {
			return true;
		}
		cancelPendingPicker();
		openTaskPicker(frm, {
			node: this.params.node,
			data: this.params.data,
			event: this.params,
			field: this.params.colDef?.field,
			anchor: this.params.eGridCell,
		});
		return true;
	}

	getGui() {
		return document.createElement("span");
	}

	getValue() {
		return this.params?.value;
	}
}

/**
 * Second click on focused cell — core click-when-active.
 * Delay so the first pulse of a dblclick does not open the picker before Form.
 */
export function onPickerActiveClick(event) {
	const field = event?.colDef?.field || event?.column?.getColId?.();
	const rowIndex = event?.node?.rowIndex;
	if (rowIndex == null || !PICKER_FIELDS.includes(field)) {
		return;
	}
	cancelPendingPicker();
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
		event.api?.startEditingCell?.({ rowIndex, colKey: field });
	}, 220);
}
