import {
	dayField,
	descField,
	getDatesBetween,
	sumDayHours,
} from "./model.js";
import { taskLabelFromCatalog } from "./catalog.js";

function leaveHoursForDate(frm, leave, date) {
	const leaveDates = getDatesBetween(leave.alfrom_date, leave.alto_date);
	if (!leaveDates.includes(date)) {
		return 0;
	}
	if (date === leave.alfrom_date) {
		return flt(leave.alfrom_hours) || 0;
	}
	if (date === leave.alto_date) {
		return flt(leave.alto_hours) || 0;
	}
	const reduced = (frm.ut.workHours || []).find((d) => d.wht_date === date);
	return flt(reduced?.wht_hours ?? frm.template_doc?.hours_on_date) || 0;
}

export function positionToRow(frm, position) {
	const dates = frm.ut.dates || [];
	const row = {
		id: String(position.name),
		rowType: "position",
		isNew: !!position.new,
		project: position.project || "",
		project_label: position.project_label || position.project || "",
		document_type: position.document_type || "Task",
		document_name: position.document_name || "",
		document_label:
			position.document_label ||
			taskLabelFromCatalog(frm, position.document_name) ||
			position.document_name ||
			"",
		project_role: position.project_role || "",
		status: position.status || "",
		reject_reason: position.reject_reason || "",
		limit_icon: "",
		limit_status: "",
		limit_tooltip: "",
	};

	const byDate = {};
	for (const d of position.details || []) {
		byDate[d.date] = d;
	}
	for (const date of dates) {
		const detail = byDate[date];
		row[dayField(date)] = detail ? flt(detail.hours) || 0 : 0;
		row[descField(date)] = detail?.description || "";
	}
	row.total = sumDayHours(row, dates);
	return row;
}

/** demodev: separate block header «Заявки на отсутствие:». */
function leaveSectionRow() {
	return {
		id: "ut_leave_section",
		rowType: "section",
		isNew: false,
		project: "",
		project_label: __("Leave Applications:"),
		document_type: "",
		document_name: "",
		document_label: "",
		project_role: "",
		status: "",
		reject_reason: "",
		total: "",
	};
}

function leaveToRow(frm, leave) {
	const dates = frm.ut.dates || [];
	const row = {
		id: `leave_${leave.name}`,
		rowType: "leave",
		isNew: false,
		project: "",
		project_label: leave.altype_of_leave || "",
		document_type: "Application For Leave",
		document_name: leave.name,
		document_label: leave.name,
		project_role: "",
		status: "",
		reject_reason: "",
		leave,
	};
	for (const date of dates) {
		row[dayField(date)] = leaveHoursForDate(frm, leave, date);
		row[descField(date)] = "";
	}
	row.total = sumDayHours(row, dates);
	return row;
}

export function buildRows(frm) {
	const positions = frm.ts_positions || [];
	const leaves = frm.ut?.leaves || [];
	const rows = positions.map((p) => positionToRow(frm, p));
	if (leaves.length) {
		rows.push(leaveSectionRow());
		for (const leave of leaves) {
			rows.push(leaveToRow(frm, leave));
		}
	}
	return rows;
}
