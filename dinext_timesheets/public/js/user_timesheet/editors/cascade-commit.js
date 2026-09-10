export const FIELD_PROJECT = "project_label";
export const FIELD_TASK = "document_label";
export const FIELD_ROLE = "project_role";

/** Project / Task open the picker. Role is an in-cell Select. */
export const PICKER_FIELDS = [FIELD_PROJECT, FIELD_TASK];

export const CASCADE_DATA_FIELDS = [
	"project",
	"project_label",
	"document_type",
	"document_name",
	"document_label",
	"project_role",
];

export function ensureCatalog(frm) {
	const customers = frm.ut?.tasksData || frm.tasks_data;
	if (!customers || !Object.keys(customers).length) {
		frappe.msgprint(__("Список задач ещё не загружен"));
		return false;
	}
	return true;
}

function editSource() {
	return (
		(typeof DinextTable !== "undefined" &&
			DinextTable.CELL_CHANGE_SOURCES?.EDIT) ||
		"edit"
	);
}

/**
 * Canon path: one batch → validate → apply → onSaveCells → undo stack.
 * @returns {boolean}
 */
export function commitCascadePatch(frm, params, patch) {
	const table = frm.ut?.table;
	const node = params?.node;
	const row = node?.data || params?.data;
	if (!table?.commitCellChanges || !node || !row) {
		console.error("[UserTimesheet] cascade: commitCellChanges unavailable");
		return false;
	}

	const changes = [];
	for (const field of Object.keys(patch)) {
		const newValue = patch[field];
		const oldValue = row[field];
		if ((oldValue ?? "") === (newValue ?? "")) {
			continue;
		}
		changes.push({
			node,
			field,
			oldValue,
			newValue,
			rowIndex: node.rowIndex,
			colId: field,
		});
	}
	if (!changes.length) {
		return false;
	}

	const { applied } = table.commitCellChanges({
		source: editSource(),
		changes,
		alreadyApplied: false,
	});
	return applied > 0;
}
