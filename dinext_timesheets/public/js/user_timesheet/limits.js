/**
 * Plan/fact limits (demodev Check Limits_V2 + Show Plan-Actual Data_V2).
 * Single path: PWA whitelist only. No SS / bare-method fallback.
 */
import { isTaskPickerOpen } from "./editors/task-picker-modal.js";
const LIMITS_METHOD =
	"project_workload_assignment.api.calculate_user_timesheet_limits";

const LIMIT_COLORS = {
	block: "#f44336",
	message: "#FF9800",
	warning: "#FFEB3B",
	normal: "#4CAF50",
	"no-plan": "#9E9E9E",
};

/** Prefer UTP.status; fall back to workflow_state (often only that is set). */
export function positionLimitStatus(pos) {
	return (pos?.status || pos?.workflow_state || "").trim();
}

/** Sync all_hours/status from grid rows before limits API (demodev getPayload). */
export function getLimitsPayload(frm) {
	const deleted = frm.deletedPositions || [];
	const byId = {};
	for (const row of frm.ut?.rows || []) {
		if (row?.rowType === "position" && row.id != null) {
			byId[String(row.id)] = row;
		}
	}
	const positions = (frm.ts_positions || [])
		.filter((pos) => !deleted.some((del) => String(del) === String(pos.name)))
		.map((pos) => {
			const row = byId[String(pos.name)];
			const allHours =
				row != null && row.total !== "" && row.total != null
					? flt(row.total)
					: flt(pos.all_hours);
			return {
				...pos,
				status: positionLimitStatus(pos) || positionLimitStatus(row),
				all_hours: allHours,
				custom_username:
					pos.custom_username || frm.doc.timesheet_from_name || "",
			};
		});
	return {
		timesheet_name: frm.doc.name,
		positions,
	};
}

/** demodev Check Limits_V2 tooltip text. */
export function limitTooltipForResult(r) {
	if (r?.planned_hours > 0) {
		return __("{0}% of {1} h.", [r.completion_percentage, r.planned_hours]);
	}
	return __("Planned work efforts are not defined");
}

async function callLimits(args) {
	const r = await frappe.call({ method: LIMITS_METHOD, args });
	return r?.message || [];
}

/** Warnings for post-save alert (demodev checkLimits). */
export async function checkLimits(frm) {
	if (!frm.ts_positions?.length || !frm.doc.name) {
		return [];
	}
	const message = await callLimits(getLimitsPayload(frm));
	return (message || []).filter(
		(r) => r.status === "block" || r.status === "warning"
	);
}

/** Hard errors on submit Start (demodev checkPlannedHoursAndLimits). */
export async function checkPlannedHoursAndLimits(frm) {
	const errors = [];
	const warnings = [];
	try {
		const positions = frm.ts_positions || [];
		if (!positions.length || !frm.doc.name) {
			return { errors, warnings };
		}
		const message = await callLimits({
			timesheet_name: frm.doc.name,
			positions: positions.map((p) => ({
				name: p.name,
				document_name: p.document_name,
				project_role: p.project_role,
				project: p.project,
				status: positionLimitStatus(p),
				all_hours: flt(p.all_hours),
			})),
		});
		(message || []).forEach((r) => {
			if (r.status === "block") {
				if (r.planned_hours > 0) {
					const max_hrs = (r.limit * r.planned_hours) / 100;
					errors.push(
						__(
							'Work efforts for task "{0}" (role: {1}) exceeded the blocking limit ({2} h.) by {3} hour(s).',
							[r.task_subject, r.role, max_hrs, r.total_hours - max_hrs]
						)
					);
				} else {
					errors.push(
						__(
							'Mandatory planned work efforts are not defined for task "{0}" (role: {1})',
							[r.task_subject, r.role]
						)
					);
				}
			} else if (r.status === "warning") {
				warnings.push(r);
			}
		});
	} catch (error) {
		console.error("[UserTimesheet] checkPlannedHoursAndLimits", error);
		const detail =
			error?.message ||
			error?.exc ||
			error?.responseJSON?.exception ||
			String(error);
		errors.push(
			`${__("Error checking planned work efforts and limits")}: ${detail}`
		);
	}
	return { errors, warnings };
}

/**
 * Write status/tooltip onto existing row objects. No table.refresh —
 * a full rowData replace remounts cascade editors and flashes cells.
 */
export function applyLimitStyles(frm, results) {
	const byPos = {};
	(results || []).forEach((r) => {
		byPos[String(r.position)] = r;
	});
	frm.ut.limitResults = byPos;

	const api = frm.ut.table?.api;
	const changedNodes = [];
	for (const row of frm.ut.rows || []) {
		if (row.rowType !== "position") {
			continue;
		}
		const r = byPos[String(row.id)];
		const nextStatus = r?.status || "";
		const nextTooltip = limitTooltipForResult(r);
		const changed =
			row.limit_status !== nextStatus ||
			row.limit_icon !== nextStatus ||
			row.limit_tooltip !== nextTooltip;
		row.limit_status = nextStatus;
		row.limit_icon = nextStatus;
		row.limit_tooltip = nextTooltip;
		if (!changed) {
			continue;
		}
		const node = api?.getRowNode?.(String(row.id));
		if (node) {
			changedNodes.push(node);
		}
	}

	if (!api) {
		return;
	}
	api.refreshCells?.({
		rowNodes: changedNodes.length ? changedNodes : undefined,
		columns: ["limit_icon"],
		force: true,
	});
	/* redrawRows remounts the anchor row — skip while picker is open. */
	if (!isTaskPickerOpen() && changedNodes.length && api.redrawRows) {
		api.redrawRows({ rowNodes: changedNodes });
	}
}

/** Apply limit status onto position rows + refresh grid. */
export async function refreshLimits(frm) {
	if (!frm.ts_positions?.length || !frm.doc.name || !frm.ut?.table) {
		return;
	}
	let finishInflight = () => {};
	const done = new Promise((resolve) => {
		finishInflight = resolve;
	});
	frm.ut._limitsInflight = done;
	try {
		const message = await callLimits(getLimitsPayload(frm));
		applyLimitStyles(frm, message);
	} finally {
		finishInflight();
		if (frm.ut?._limitsInflight === done) {
			frm.ut._limitsInflight = null;
		}
	}
}

/** Debounced refresh after cell edit / copy / add-delete (demodev timesheetDataUpdated). */
export function scheduleRefreshLimits(frm, delayMs = 400) {
	if (!frm?.ut) {
		return;
	}
	if (frm.ut._limitsTimer) {
		clearTimeout(frm.ut._limitsTimer);
	}
	frm.ut._limitsTimer = setTimeout(() => {
		frm.ut._limitsTimer = null;
		if (isTaskPickerOpen()) {
			scheduleRefreshLimits(frm, delayMs);
			return;
		}
		refreshLimits(frm).catch((err) => {
			console.error("[UserTimesheet] scheduleRefreshLimits", err);
		});
	}, delayMs);
}

function getNoPlanWarningHtml() {
	return `
		<div class="alert alert-danger" style="margin-bottom: 15px;">
			<i class="fa fa-exclamation-triangle"></i>
			<strong> ${__("Attention!")}</strong> ${__(
				"Planned work efforts are required for this task!"
			)}
		</div>`;
}

function showForecastColumn() {
	return Boolean(frappe.boot?.dinext_timesheet_show_forecast);
}

function getCompletionTableHtml(result) {
	const calculatePercentage = (value) =>
		result.planned_hours > 0
			? Math.round((value / result.planned_hours) * 100)
			: 0;
	const showForecast = showForecastColumn();
	const forecastHours = Number.parseFloat(result.forecast_hours);
	const forecastLabel = Number.isFinite(forecastHours)
		? forecastHours.toFixed(1)
		: "0.0";
	const rows = [];
	for (const key in result.hours_data || {}) {
		if (key === "users" || key === "user_hours") {
			continue;
		}
		const raw = result.hours_data[key];
		if (raw != null && typeof raw === "object") {
			continue;
		}
		const hours = Number.parseFloat(raw);
		if (!Number.isFinite(hours)) {
			continue;
		}
		rows.push({
			status: key === "total" ? __("All") : __(key),
			isTotal: key === "total",
			plan: Number.parseFloat(result.planned_hours).toFixed(1),
			forecast: forecastLabel,
			fact: `${hours.toFixed(1)} ${__("h.")}`,
			percent: calculatePercentage(hours),
		});
	}
	const forecastTh = showForecast
		? `<th style="width: 15%; text-align: right;">${__("Forecast")}</th>`
		: "";
	const statusWidth = showForecast ? "25%" : "30%";
	const planWidth = showForecast ? "15%" : "20%";
	const factWidth = showForecast ? "15%" : "20%";
	return `
		<div class="frappe-table-container" style="margin-bottom: 15px;">
			<table class="table table-bordered" style="width: 100%; margin-bottom: 10px;">
				<thead>
					<tr>
						<th style="width: ${statusWidth};">${__("Status")}</th>
						<th style="width: ${planWidth}; text-align: right;">${__("Plan")}</th>
						${forecastTh}
						<th style="width: ${factWidth}; text-align: right;">${__("Fact")}</th>
						<th style="width: 30%;">${__("% Complete")}</th>
					</tr>
				</thead>
				<tbody>
					${rows
						.map(
							(row) => `
						<tr ${row.isTotal ? 'style="font-weight: bold;"' : ""}>
							<td>${frappe.utils.escape_html(row.status)}</td>
							<td style="text-align: right;">${row.plan}</td>
							${
								showForecast
									? `<td style="text-align: right;">${row.forecast}</td>`
									: ""
							}
							<td style="text-align: right;">${row.fact}</td>
							<td>
								<div class="progress" style="height: 20px; margin-bottom: 0;">
									<div class="progress-bar ${
										row.percent > 100
											? "progress-bar-danger"
											: "progress-bar-success"
									}"
										role="progressbar"
										style="width: ${Math.min(row.percent, 100)}%;">
										${row.percent <= 100 ? `${row.percent}%` : `${row.percent}%`}
									</div>
								</div>
							</td>
						</tr>`
						)
						.join("")}
				</tbody>
			</table>
		</div>`;
}

function getHoursUsers(result, frm) {
	let users = [...(result.hours_data?.users || [])];
	users.push(frm.doc.timesheet_from_name);
	users = [...new Set(users)].filter((user) => user);
	if (!users.length) {
		return "";
	}
	return `<br>${__("Hours included from:")} ${frappe.utils.comma_and(users)}`;
}

function getHoursNoteHtml(result) {
	if (result.used_children_for_actual) {
		return __("Fact data: including other child tasks ({0})", [
			result.child_tasks_count,
		]);
	}
	return __("Fact data: current task only");
}

function getCurrentUserHoursHtml(result, frm) {
	const ownerFullName = frm.doc.timesheet_from_name;
	if (!ownerFullName) {
		return "";
	}
	const ownerHoursByStatus = result.hours_data?.user_hours?.[ownerFullName] || {};
	let totalOwnerHours = 0;
	for (const status in ownerHoursByStatus) {
		if (typeof ownerHoursByStatus[status] !== "number") {
			continue;
		}
		totalOwnerHours += ownerHoursByStatus[status];
	}
	if (totalOwnerHours === 0) {
		return "";
	}
	const percentage =
		result.planned_hours > 0
			? Math.round((totalOwnerHours / result.planned_hours) * 100)
			: 0;
	const statuses = Object.keys(ownerHoursByStatus);
	let statusBreakdown = "";
	if (statuses.length > 1) {
		statusBreakdown = `<br><small class="ut-limits-muted">${statuses
			.map(
				(status) =>
					`${frappe.utils.escape_html(__(status))}: ${ownerHoursByStatus[status].toFixed(2)} ${__("h.")}`
			)
			.join(" | ")}</small>`;
	} else if (statuses.length === 1) {
		statusBreakdown = `<br><small class="ut-limits-muted">${__("Status")}: ${frappe.utils.escape_html(
			__(statuses[0])
		)}</small>`;
	}
	return `
		<div class="ut-limits-owner">
			<strong>${frappe.utils.escape_html(ownerFullName)}:</strong>
			<span class="ut-limits-owner__hours">${totalOwnerHours.toFixed(2)} ${__("h.")}</span>
			${
				result.planned_hours > 0
					? `<span class="ut-limits-muted"> (${percentage}% ${__("of plan")})</span>`
					: ""
			}
			${statusBreakdown}
		</div>`;
}

function getParentTaskInfoHtml(result) {
	if (result.planned_hours <= 0) {
		return "";
	}
	let html = `<div class="hours-note">${__(
		"Planned data is defined at:"
	)} ${frappe.utils.escape_html(result.plan_task_subject || "")}</div>`;
	const sources = result.plan_sources || [];
	if (sources.length) {
		html += `<div class="hours-note">${__("Plan sources:")}<ul>`;
		for (const source of sources) {
			html += `<li>${frappe.utils.escape_html(source.subject || "")} (${frappe.utils.escape_html(
				source.task_name || ""
			)}): ${source.planned_hours} ${__("h.")}</li>`;
		}
		html += `</ul></div>`;
	}
	return html;
}

function limitResultFor(frm, position) {
	const key = String(position?.name || position?.id || "");
	if (!key) {
		return null;
	}
	return frm.ut?.limitResults?.[key] || null;
}

/** Plan/fact modal for a position row (demodev showTaskPlanFact). */
export async function showTaskPlanFact(frm, position) {
	if (!position?.document_name) {
		frappe.msgprint(__("No task selected to display information"));
		return;
	}
	let result = limitResultFor(frm, position);
	if (!result && frm.ut?._limitsInflight) {
		await frm.ut._limitsInflight;
		result = limitResultFor(frm, position);
	}
	if (!result) {
		if (!frm.ut._limitDialogInflight) {
			frm.ut._limitDialogInflight = callLimits(getLimitsPayload(frm))
				.then((message) => {
					applyLimitStyles(frm, message);
					return message;
				})
				.finally(() => {
					if (frm.ut) {
						frm.ut._limitDialogInflight = null;
					}
				});
		}
		await frm.ut._limitDialogInflight;
		result = limitResultFor(frm, position);
	}
	if (!result) {
		frappe.msgprint(__("No plan/fact data for the position"));
		return;
	}

	const d = new frappe.ui.Dialog({
		title: result.task_subject || position.document_name,
		size: "large",
		fields: [
			{
				fieldtype: "HTML",
				fieldname: "body",
			},
		],
		primary_action_label: __("Close"),
		primary_action() {
			d.hide();
		},
	});
	const html =
		(result.planned_hours <= 0 && result.plan_required
			? getNoPlanWarningHtml()
			: "") +
		getCompletionTableHtml(result) +
		getHoursNoteHtml(result) +
		getCurrentUserHoursHtml(result, frm) +
		getHoursUsers(result, frm) +
		getParentTaskInfoHtml(result);
	d.fields_dict.body.$wrapper.html(html);
	d.show();
}

export function limitIconColor(status) {
	return LIMIT_COLORS[status] || "";
}

/** After save: yellow alert for warning/block positions (non-blocking). */
export async function alertLimitWarnings(frm) {
	let warningCheck = await checkLimits(frm);
	if (!warningCheck.length) {
		return;
	}
	const uniq = [];
	const seen = new Set();
	for (const w of warningCheck) {
		const key = JSON.stringify(w);
		if (seen.has(key)) {
			continue;
		}
		seen.add(key);
		uniq.push(w);
	}
	const message = uniq
		.map(
			(w) =>
				`• <b>${frappe.utils.escape_html(w.task_subject)}</b> (${__(
					"Project"
				)}: ${frappe.utils.escape_html(w.project)}, ${__("Role")}: ${frappe.utils.escape_html(
					w.role
				)})<br>` +
				`&nbsp;&nbsp;${__("Fact work efforts")}: ${
					w.completion_percentage
				}% ${__("of plan")}`
		)
		.join("<br><br>");
	frappe.show_alert(
		{
			message: `<b>${__("Please review the following tasks:")}</b><br><br>${message}`,
			indicator: "yellow",
		},
		15
	);
}
