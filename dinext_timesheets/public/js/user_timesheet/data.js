import { initState } from "./state.js";
import { getDatesBetween } from "./model.js";
import { buildRows } from "./rows.js";
import { buildSummaryRows } from "./summary.js";
import {
	projectLabelFromCatalog,
	taskLabelFromCatalog,
} from "./catalog.js";

async function loadTemplate(frm) {
	const r = await frappe.db.get_value(
		"Worker",
		{ wuser: frm.doc.timesheet_from },
		"wtimesheet_template"
	);
	const templateName = r?.message?.wtimesheet_template;
	if (!templateName) {
		frm.template_doc = null;
		return;
	}
	frm.template_doc = await frappe.db.get_doc("Timesheet Template", templateName);
}

async function loadWorkHours(frm) {
	const name = frm.template_doc?.tt_working_hours_on_date;
	if (!name) {
		return [];
	}
	const doc = await frappe.db.get_doc("Working Hours On Date", name);
	return doc.hod_working_hours_table || [];
}

async function loadHolidays(frm) {
	const r = await frappe.db.get_value(
		"Worker",
		{ wuser: frm.doc.timesheet_from },
		"wholiday_list"
	);
	const listName = r?.message?.wholiday_list;
	if (!listName) {
		return [];
	}
	const doc = await frappe.db.get_doc("Holiday List", listName);
	const from = frm.doc.ts_valid_from;
	const to = frm.doc.ts_valid_for;
	return (doc.holidays || []).filter((h) => {
		const d = h.holiday_date;
		return d >= from && d <= to;
	});
}

async function loadLeaves(frm) {
	return frappe.db.get_list("Application For Leave", {
		fields: [
			"name",
			"lauser",
			"alfrom_date",
			"alto_date",
			"alreasons",
			"altype_of_leave",
			"alfrom_hours",
			"alto_hours",
		],
		filters: [
			["lauser", "=", frm.doc.timesheet_from],
			["alfrom_date", "<=", frm.doc.ts_valid_for],
			["alto_date", ">=", frm.doc.ts_valid_from],
			["status", "=", "Согласовано"],
		],
		limit: 1000,
	});
}

async function loadRejectReason(positionName) {
	const comments = await frappe.db.get_list("Comment", {
		filters: [
			["reference_doctype", "=", "User Timesheet Position"],
			["reference_name", "=", positionName],
		],
		fields: ["content", "comment_by"],
		limit: 1,
		order_by: "creation desc",
	});
	if (!comments?.length) {
		return "";
	}
	const author =
		frappe.boot.user_info?.[comments[0].comment_by]?.fullname || comments[0].comment_by;
	return $("<div>")
		.html(`${frappe.utils.escape_html(author)}: ${comments[0].content || ""}`)
		.text();
}

async function loadPositions(frm) {
	const list = await frappe.db.get_list("User Timesheet Position", {
		filters: [["user_timesheet", "=", frm.doc.name]],
		fields: [
			"name",
			"project",
			"project_role",
			"document_type",
			"document_name",
			"status",
			"workflow_state",
			"all_hours",
			"custom_username",
		],
		limit: 0,
		order_by: "creation asc",
	});

	const positions = [];
	for (const item of list) {
		const doc = await frappe.db.get_doc("User Timesheet Position", item.name);
		const details = (doc.table || []).filter(
			(d) => d.date >= frm.doc.ts_valid_from && d.date <= frm.doc.ts_valid_for
		);
		const status = (item.status || item.workflow_state || "").trim();
		let reject_reason = "";
		if (status === "Отклонено") {
			reject_reason = await loadRejectReason(item.name);
		}
		const hoursFromDetails = details.reduce((sum, d) => sum + (flt(d.hours) || 0), 0);
		positions.push({
			...item,
			status,
			workflow_state: item.workflow_state || status,
			user: item.user || frm.doc.timesheet_from,
			custom_username:
				item.custom_username || frm.doc.timesheet_from_name || "",
			all_hours: hoursFromDetails || flt(item.all_hours) || 0,
			details,
			reject_reason,
			new: false,
		});
	}
	return positions;
}

export async function loadTitles(positions, frm) {
	const projectIds = [...new Set(positions.map((p) => p.project).filter(Boolean))];
	const projectNames = {};
	await Promise.all(
		projectIds.map(async (name) => {
			const catalog = frm ? projectLabelFromCatalog(frm, name) : "";
			const r = await frappe.db.get_value("Project", name, "project_name");
			projectNames[name] = r?.message?.project_name || catalog || name;
		})
	);

	await Promise.all(
		positions.map(async (p) => {
			p.project_label =
				projectNames[p.project] ||
				(frm ? projectLabelFromCatalog(frm, p.project) : "") ||
				p.project ||
				"";
			if (!p.document_type || !p.document_name) {
				p.document_label = "";
				return;
			}
			const catalog = frm ? taskLabelFromCatalog(frm, p.document_name) : "";
			let subject = "";
			try {
				const r = await frappe.db.get_value(
					p.document_type,
					p.document_name,
					"subject"
				);
				subject = r?.message?.subject || "";
			} catch (_err) {
				subject = "";
			}
			p.document_label = subject || catalog || p.document_name;
		})
	);
}

async function loadTasksData(frm) {
	if (!frm.template_doc?.name) {
		return null;
	}
	const res = await frappe.call({
		method: "dinext_timesheets.dinext_timesheets.user_timesheet.api.get_timesheet_tasks",
		args: {
			template_name: frm.template_doc.name,
			ts_start: frm.doc.ts_valid_from,
			ts_end: frm.doc.ts_valid_for,
			ts_owner: frm.doc.timesheet_from,
		},
	});
	return res.message || null;
}

/** Load UT grid domain into frm.ut / frm.ts_positions. */
export async function loadGridData(frm) {
	const state = initState(frm);
	await loadTemplate(frm);

	const dates = getDatesBetween(frm.doc.ts_valid_from, frm.doc.ts_valid_for);
	if (!dates.length) {
		frappe.throw(__("Ошибка определения дат ТШ!"));
	}

	const [workHours, holidays, leaves, positions, tasksData] = await Promise.all([
		loadWorkHours(frm),
		loadHolidays(frm),
		loadLeaves(frm),
		loadPositions(frm),
		loadTasksData(frm),
	]);

	state.tasksData = tasksData;
	frm.tasks_data = tasksData;
	await loadTitles(positions, frm);

	state.dates = dates;
	state.workHours = workHours;
	state.holidays = holidays;
	state.leaves = leaves;
	frm.dates = dates;
	frm.holidays = holidays;
	frm.work_hours = workHours;
	frm.ts_positions = positions;

	state.rows = buildRows(frm);
	state.summaryRows = buildSummaryRows(frm);
	return state;
}

export async function reloadTable(frm, initTable, refreshRuntime) {
	const state = initState(frm);
	if (!state.table) {
		return initTable(frm);
	}
	await loadGridData(frm);
	await refreshRuntime(frm);
	return state.table;
}
