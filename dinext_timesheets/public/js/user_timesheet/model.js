import {
	FIELD_PROJECT,
	FIELD_ROLE,
	FIELD_TASK,
} from "./editors/cascade-commit.js";

/**
 * Editable when draft/rework and caller is owner, System Manager, or team lead
 * (frm.ut.isTeamLead set in form_chrome via team_lead.js).
 */
/** V10 disableReprocessJournalEntries. Prod: Z_Dinord_*; local/dinext: Dinext_*. */
const REPROCESS_ROLES = [
	"Dinext_Projects_Director",
	"Dinext_Projects_Admin",
	"Z_Dinord_Projects_Director",
	"Z_Dinord_Projects_Admin",
];

export function canReprocessJournalEntries() {
	return REPROCESS_ROLES.some((role) => !!frappe.user?.has_role?.(role));
}

export function canEdit(frm) {
	const status = frm.doc?.ut_status;
	if (status !== "Черновик" && status !== "На доработке") {
		return false;
	}
	const user = frappe.session.user;
	if (user === frm.doc?.timesheet_from) {
		return true;
	}
	if (frappe.user?.has_role?.("System Manager")) {
		return true;
	}
	if (frm.ut?.isTeamLead) {
		return true;
	}
	return false;
}

export function dayField(date) {
	return `day_${date}`;
}

export function descField(date) {
	return `desc_${date}`;
}

export function getDatesBetween(from, to) {
	const dates = [];
	if (!from || !to) {
		return dates;
	}
	let cursor = from;
	while (frappe.datetime.get_day_diff(cursor, to) <= 0) {
		dates.push(cursor);
		cursor = frappe.datetime.add_days(cursor, 1);
	}
	return dates;
}

export function isHoliday(holidays, date) {
	return (holidays || []).some((h) => h.holiday_date === date);
}

export function sumDayHours(row, dates) {
	let total = 0;
	for (const date of dates) {
		total += flt(row[dayField(date)]) || 0;
	}
	return total;
}

const POSITION_SYNC_FIELDS = new Set([
	"project",
	"project_label",
	"document_type",
	"document_name",
	"document_label",
	"project_role",
]);

/** Apply grid cell batch into row + matching frm.ts_positions entry. */
export function applyCellChanges(frm, changes) {
	const state = frm.ut;
	const dates = state?.dates || [];
	const rowsToSync = new Set();

	for (const change of changes) {
		if (change.section === "summary") {
			continue;
		}
		const row = (state.rows || []).find((r) => String(r.id) === String(change.rowId));
		if (!row || row.rowType === "section" || row.rowType === "leave") {
			continue;
		}
		if (row.rowType !== "position") {
			continue;
		}
		row[change.field] = change.newValue;

		if (change.field?.startsWith("day_")) {
			row.total = sumDayHours(row, dates);
			rowsToSync.add(row);
		} else if (POSITION_SYNC_FIELDS.has(change.field)) {
			rowsToSync.add(row);
		}
	}

	for (const row of rowsToSync) {
		syncPositionFromRow(frm, row);
	}
}

export function syncPositionFromRow(frm, row) {
	const positions = frm.ts_positions || [];
	let pos = positions.find((p) => String(p.name) === String(row.id));
	if (!pos) {
		pos = { name: row.id, details: [], new: row.isNew };
		positions.push(pos);
	}
	pos.project = row.project || "";
	pos.project_label = row.project_label || "";
	pos.project_role = row.project_role || "";
	pos.document_type = row.document_type || "Task";
	pos.document_name = row.document_name || "";
	pos.document_label = row.document_label || "";
	pos.status = row.status || pos.status || "";
	pos.new = !!row.isNew;
	pos.all_hours = row.total;

	const dates = frm.ut?.dates || [];
	const details = [];
	for (const date of dates) {
		const hours = flt(row[dayField(date)]) || 0;
		const description = String(row[descField(date)] || "").trim();
		if (hours > 0 || description) {
			details.push({ date, hours, description });
		}
	}
	pos.details = details;
}

export function positionStatusForSave(frm) {
	const st = frm.doc.ut_status;
	if (st === "Черновик" || st === "На доработке") {
		return "Редактирование";
	}
	if (st === "Согласован") {
		return "Согласовано";
	}
	return st;
}

/** Same key as copy.js: type + doc + project + role. */
export function positionSignature(row) {
	return [
		row?.document_type || "Task",
		row?.document_name || "",
		row?.project || "",
		row?.project_role || "",
	].join("::");
}

/**
 * Duplicate complete cascade rows → errors + invalid marks on all twins.
 * Incomplete rows (missing project/task/role) skipped — other validators own them.
 */
export function collectDuplicatePositionErrors(positionRows, errors, invalidCells) {
	const groups = new Map();
	(positionRows || []).forEach((row, idx) => {
		if (!row?.project || !row.document_name || !row.project_role) {
			return;
		}
		const sig = positionSignature(row);
		if (!groups.has(sig)) {
			groups.set(sig, []);
		}
		groups.get(sig).push({ row, line: idx + 1 });
	});

	for (const group of groups.values()) {
		if (group.length < 2) {
			continue;
		}
		const lines = group.map((g) => g.line).join(", ");
		errors.push(
			__("Дублируются строки {0}: одинаковые проект, задача и роль", [lines])
		);
		for (const { row } of group) {
			invalidCells.push({ rowId: row.id, field: FIELD_PROJECT });
			invalidCells.push({ rowId: row.id, field: FIELD_TASK });
			invalidCells.push({ rowId: row.id, field: FIELD_ROLE });
		}
	}
}

/** New row with no cascade and no hours/descriptions — skip insert. */
function isFullyEmptyPositionRow(row, dates) {
	if (row.project || row.document_name || row.project_role) {
		return false;
	}
	for (const date of dates || []) {
		if (flt(row[dayField(date)]) || String(row[descField(date)] || "").trim()) {
			return false;
		}
	}
	return true;
}

/** Build insert/update docs from current rows (model, not DOM). */
export function buildSavePayload(frm) {
	const state = frm.ut;
	const dates = state?.dates || [];
	const errors = [];
	const invalidCells = [];
	const newPositions = [];
	const updatedPositions = [];

	const positionRows = (state?.rows || []).filter((r) => r.rowType === "position");
	collectDuplicatePositionErrors(positionRows, errors, invalidCells);

	positionRows.forEach((row) => {
		const table = [];
		for (const date of dates) {
			const hours = flt(row[dayField(date)]) || 0;
			const description = String(row[descField(date)] || "").trim();
			if (hours > 0 || description) {
				table.push({ date, hours, description });
			}
		}

		if (row.isNew && isFullyEmptyPositionRow(row, dates)) {
			return;
		}

		const doc = {
			doctype: "User Timesheet Position",
			parent: frm.doc.name,
			user_timesheet: frm.doc.name,
			user: frm.doc.timesheet_from,
			document_type: row.document_type || "Task",
			document_name: row.document_name || "",
			project: row.project || "",
			project_role: row.project_role || "",
			status: positionStatusForSave(frm),
			all_hours: sumDayHours(row, dates),
			table,
		};

		if (row.isNew) {
			newPositions.push(doc);
		} else {
			updatedPositions.push({ ...doc, name: row.id, docname: row.id });
		}
	});

	return {
		errors,
		invalidCells,
		newPositions,
		updatedPositions,
		deleted: frm.deletedPositions || [],
	};
}
