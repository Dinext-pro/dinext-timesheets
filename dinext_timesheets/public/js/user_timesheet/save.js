import { applyCellChanges, buildSavePayload, canEdit } from "./model.js";
import { buildSummaryRows } from "./summary.js";
import { scheduleRefreshLimits } from "./limits.js";
import { CASCADE_DATA_FIELDS } from "./editors/cascade-commit.js";
import {
	clearInvalidAfterEdit,
	clearInvalidCells,
	setInvalidCells,
} from "./invalid-cells.js";
import { syncStartButtonState } from "./submit.js";

/**
 * Persist UTP from model (demodev saveTimesheet semantics).
 * @returns {Promise<boolean>}
 */
export async function saveTimesheetPositions(frm) {
	const { errors, invalidCells, newPositions, updatedPositions, deleted } =
		buildSavePayload(frm);

	if (errors.length) {
		setInvalidCells(frm, invalidCells);
		frappe.validated = false;
		frappe.msgprint({
			title: __("Cannot save timesheet"),
			indicator: "red",
			as_list: true,
			message: errors,
		});
		return false;
	}

	clearInvalidCells(frm);

	const remainingDeleted = [...deleted];
	for (const id of deleted) {
		try {
			await frappe.call({
				method: "frappe.client.delete",
				args: { doctype: "User Timesheet Position", name: id },
				freeze: true,
				silent: true,
			});
			const idx = remainingDeleted.indexOf(id);
			if (idx >= 0) {
				remainingDeleted.splice(idx, 1);
			}
		} catch (err) {
			console.error(`[UserTimesheet] delete ${id}`, err);
			frm.deletedPositions = remainingDeleted;
			frappe.validated = false;
			frappe.msgprint({
				title: __("Save Error"),
				indicator: "red",
				message: __("Error deleting position {0}", [id]),
			});
			return false;
		}
	}
	frm.deletedPositions = [];

	if (newPositions.length) {
		try {
			await frappe.call({
				method: "frappe.client.insert_many",
				args: { docs: newPositions },
				freeze: true,
				silent: true,
				freeze_message: __("Saving data..."),
			});
		} catch (err) {
			console.error("[UserTimesheet] insert_many", err);
			frappe.validated = false;
			frappe.msgprint({
				title: __("Save Error"),
				indicator: "red",
				message: __("Error saving new positions"),
			});
			return false;
		}
	}

	if (updatedPositions.length) {
		try {
			await frappe.call({
				method: "frappe.client.bulk_update",
				args: { docs: updatedPositions },
				freeze: true,
				silent: true,
				freeze_message: __("Saving data..."),
			});
		} catch (err) {
			console.error("[UserTimesheet] bulk_update", err);
			frappe.validated = false;
			frappe.msgprint({
				title: __("Save Error"),
				indicator: "red",
				message: __("Error updating positions"),
			});
			return false;
		}
	}

	return true;
}

export function onValidateCells(frm, ctx) {
	if (!frm.ut) {
		return true;
	}
	/* Hard gate: Согласован / На согласовании / Отклонено — no cell commits. */
	if (!canEdit(frm)) {
		return __("Editing is not available in the current status");
	}
	for (const change of ctx.changes) {
		if (change.section === "summary") {
			return __("The total row cannot be edited");
		}
		const row = (frm.ut.rows || []).find((r) => String(r.id) === String(change.rowId));
		if (row?.rowType === "section") {
			return __("Service row");
		}
		if (row?.rowType === "leave") {
			return __("Leave applications are read-only");
		}
		if (change.field?.startsWith("day_")) {
			const n = flt(change.newValue);
			if (change.newValue !== "" && change.newValue != null && Number.isNaN(n)) {
				return __("Hours must be a number");
			}
			if (n < 0) {
				return __("Hours cannot be negative");
			}
		}
	}
	return true;
}

function collectChangeNodes(frm, changes, predicate) {
	const api = frm.ut.table?.api;
	const seen = new Set();
	const nodes = [];
	for (const change of changes || []) {
		if (predicate && !predicate(change)) {
			continue;
		}
		const id = String(change.rowId);
		if (seen.has(id)) {
			continue;
		}
		seen.add(id);
		const node = api?.getRowNode?.(id);
		if (node) {
			nodes.push(node);
		}
	}
	return nodes;
}

function refreshTotalsAfterDayEdit(frm, changes) {
	const dayChanges = (changes || []).filter((c) => c.field?.startsWith("day_"));
	if (!dayChanges.length) {
		return false;
	}

	frm.ut.summaryRows = buildSummaryRows(frm);
	frm.ut.table?.setSummaryRows?.(frm.ut.summaryRows);

	/* Full refresh(same rowData ref) often skips redraw — force total cells. */
	const api = frm.ut.table?.api;
	const nodes = collectChangeNodes(frm, dayChanges);
	for (const node of nodes) {
		const rowId = node.data?.id ?? node.id;
		const row = (frm.ut.rows || []).find((r) => String(r.id) === String(rowId));
		if (row && node.data && node.data !== row) {
			node.data.total = row.total;
		}
	}
	api?.refreshCells?.({
		rowNodes: nodes.length ? nodes : undefined,
		columns: ["total"],
		force: true,
	});
	return true;
}

export function onSaveCells(frm, ctx) {
	applyCellChanges(frm, ctx.changes);

	for (const change of ctx.changes || []) {
		clearInvalidAfterEdit(frm, change.rowId, change.field);
	}

	const dayEdited = refreshTotalsAfterDayEdit(frm, ctx.changes);
	/* Cascade: grid already refreshed by commitCellChanges.applyCellValue — no table.refresh. */
	const cascadeEdited = (ctx.changes || []).some((c) =>
		CASCADE_DATA_FIELDS.includes(c.field)
	);
	if (!dayEdited && !cascadeEdited && frm.ut.table?.refresh) {
		frm.ut.summaryRows = buildSummaryRows(frm);
		frm.ut.table.setSummaryRows?.(frm.ut.summaryRows);
		frm.ut.table.refresh(frm.ut.rows);
	}

	const limitsTouched = (ctx.changes || []).some(
		(c) =>
			c.field?.startsWith("day_") ||
			c.field === "project_role" ||
			c.field === "project" ||
			c.field === "document_name"
	);
	if (limitsTouched) {
		scheduleRefreshLimits(frm);
	}
	frm.dirty();
	syncStartButtonState(frm);
}
