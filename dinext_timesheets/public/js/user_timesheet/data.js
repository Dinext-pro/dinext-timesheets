import { initState } from "./state.js";
import { getDatesBetween } from "./model.js";
import { buildRows } from "./rows.js";
import { buildSummaryRows } from "./summary.js";
import {
	projectLabelFromCatalog,
	taskLabelFromCatalog,
} from "./catalog.js";

const CONTEXT = "dinext_timesheets.dinext_timesheets.user_timesheet.api.get_timesheet_context";

async function getList(doctype, args) {
	const { message } = await frappe.call({
		method: "frappe.desk.reportview.get_list",
		type: "GET",
		args: { doctype, ...args },
	});
	return message;
}

async function loadLeaves(frm) {
	return getList("Application For Leave", {
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
			["status", "=", "Approved"],
		],
		limit: 1000,
	});
}

async function rejectAuthorLabel(userId) {
	if (!userId) {
		return "";
	}
	const cached = frappe.boot.user_info?.[userId]?.fullname;
	if (cached) {
		return cached;
	}
	const r = await frappe.db.get_value("User", userId, "full_name");
	return r?.message?.full_name || userId;
}

const STATUS_ONLY_COMMENTS = new Set([
	"Editing",
	"Pending Approval",
	"Approved",
	"Rejected",
	"Draft",
	"Rework",
	"Редактирование",
	"На согласовании",
	"Согласовано",
	"Согласован",
	"Отклонено",
	"Черновик",
	"На доработке",
]);

function commentPlainText(content) {
	return $("<div>")
		.html(content || "")
		.text()
		.trim();
}

function isSkippedRejectComment(text) {
	if (!text || STATUS_ONLY_COMMENTS.has(text)) {
		return true;
	}
	return /shared this document|Создана задача/i.test(text);
}

/** Latest human Comment on UTP when the position field is empty. */
async function loadRejectReason(positionName) {
	const comments = await getList("Comment", {
		filters: [
			["reference_doctype", "=", "User Timesheet Position"],
			["reference_name", "=", positionName],
		],
		fields: ["content", "comment_by", "comment_email"],
		limit: 20,
		order_by: "creation desc",
	});
	const comment = (comments || []).find(
		(item) => !isSkippedRejectComment(commentPlainText(item.content))
	);
	if (!comment) {
		return "";
	}
	const text = commentPlainText(comment.content);
	const author = await rejectAuthorLabel(
		comment.comment_by || comment.comment_email
	);
	if (!author) {
		return text;
	}
	return `${author}: ${text}`;
}

async function loadPositions(frm) {
	const list = await getList("User Timesheet Position", {
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
		order_by: "creation asc, name asc",
	});

	const positions = [];
	for (const item of list) {
		const doc = await frappe.db.get_doc("User Timesheet Position", item.name);
		const details = (doc.table || []).filter(
			(d) => d.date >= frm.doc.ts_valid_from && d.date <= frm.doc.ts_valid_for
		);
		const status = (item.status || item.workflow_state || "").trim();
		let reject_reason = "";
		if (status === "Rejected") {
			reject_reason = String(doc.reject_reason || "").trim();
			if (!reject_reason) {
				reject_reason = await loadRejectReason(item.name);
			}
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

export function loadTitles(positions, frm) {
	for (const position of positions) {
		position.project_label = projectLabelFromCatalog(frm, position.project) || position.project || "";
		position.document_label =
			taskLabelFromCatalog(frm, position.document_name) || position.document_name || "";
	}
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
	const { message: context } = await frappe.call({
		method: CONTEXT,
		args: { timesheet: frm.doc.name },
	});
	frm.template_doc = context.template;
	state.canEdit = context.can_edit;
	const { work_hours: workHours, holidays } = context;

	const dates = getDatesBetween(frm.doc.ts_valid_from, frm.doc.ts_valid_for);
	if (!dates.length) {
		frappe.throw(__("Could not determine timesheet dates"));
	}

	const [leaves, positions, tasksData] = await Promise.all([
		loadLeaves(frm),
		loadPositions(frm),
		loadTasksData(frm),
	]);

	state.tasksData = tasksData;
	frm.tasks_data = tasksData;
	loadTitles(positions, frm);

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
