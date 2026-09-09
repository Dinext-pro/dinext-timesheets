/**
 * Plan/fact limits (demodev Check Limits_V2 + Show Plan-Actual Data_V2).
 * Single path: PWA whitelist only. No SS / bare-method fallback.
 */
import { isCascadeSelectOpen } from "./editors/cascade-select.js";
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
		return `${r.completion_percentage}% из ${r.planned_hours} ч.`;
	}
	return __("Не определены плановые трудозатраты");
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
						`Трудозатраты по задаче "${r.task_subject}" (роль: ${r.role}) ` +
							`превысили блокирующий лимит (${max_hrs} ч.) ` +
							`на ${r.total_hours - max_hrs} часа(ов).`
					);
				} else {
					errors.push(
						`Для задачи "${r.task_subject}" (роль: ${r.role}) ` +
							`не определены обязательные плановые трудозатраты`
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
			`${__("Ошибка при проверке плановых трудозатрат и лимитов")}: ${detail}`
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
	/* redrawRows remounts the whole row — skip while cascade <select> is open. */
	if (!isCascadeSelectOpen() && changedNodes.length && api.redrawRows) {
		api.redrawRows({ rowNodes: changedNodes });
	}
}

/** Apply limit status onto position rows + refresh grid. */
export async function refreshLimits(frm) {
	if (!frm.ts_positions?.length || !frm.doc.name || !frm.ut?.table) {
		return;
	}
	const message = await callLimits(getLimitsPayload(frm));
	applyLimitStyles(frm, message);
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
		if (isCascadeSelectOpen()) {
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
			<strong> ${__("Внимание!")}</strong> ${__(
				"Для этой задачи обязательно указание плановых трудозатрат!"
			)}
		</div>`;
}

function getCompletionTableHtml(result) {
	const calculatePercentage = (value) =>
		result.planned_hours > 0
			? Math.round((value / result.planned_hours) * 100)
			: 0;
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
			status: key === "total" ? __("Всего") : key,
			isTotal: key === "total",
			plan: Number.parseFloat(result.planned_hours).toFixed(1),
			fact: `${hours.toFixed(1)} ч.`,
			percent: calculatePercentage(hours),
		});
	}
	return `
		<div class="frappe-table-container" style="margin-bottom: 15px;">
			<table class="table table-bordered" style="width: 100%; margin-bottom: 10px;">
				<thead>
					<tr>
						<th style="width: 30%;">${__("Статус")}</th>
						<th style="width: 20%; text-align: right;">${__("План")}</th>
						<th style="width: 20%; text-align: right;">${__("Факт")}</th>
						<th style="width: 30%;">${__("% выполнения")}</th>
					</tr>
				</thead>
				<tbody>
					${rows
						.map(
							(row) => `
						<tr ${row.isTotal ? 'style="font-weight: bold;"' : ""}>
							<td>${frappe.utils.escape_html(row.status)}</td>
							<td style="text-align: right;">${row.plan}</td>
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
	return `<br>${__("Учтены часы от:")} ${frappe.utils.comma_and(users)}`;
}

function getHoursNoteHtml(result) {
	if (result.used_children_for_actual) {
		return `${__("Фактические данные: с учетом других дочерних задач")} (${
			result.child_tasks_count
		} шт.)`;
	}
	return __("Фактические данные: только текущая задача");
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
		statusBreakdown = `<br><small style="color: #6c757d;">${statuses
			.map(
				(status) =>
					`${frappe.utils.escape_html(status)}: ${ownerHoursByStatus[status].toFixed(2)} ${__("ч.")}`
			)
			.join(" | ")}</small>`;
	} else if (statuses.length === 1) {
		statusBreakdown = `<br><small style="color: #6c757d;">${__("Статус")}: ${frappe.utils.escape_html(
			statuses[0]
		)}</small>`;
	}
	return `
		<div style="margin: 15px 0; padding: 8px 10px; background-color: #f0f7ff; border-radius: 4px; border-left: 4px solid #007bff;">
			<strong>${frappe.utils.escape_html(ownerFullName)}:</strong>
			<span style="font-size: 16px; font-weight: bold; color: #007bff;">${totalOwnerHours.toFixed(2)} ${__("ч.")}</span>
			${
				result.planned_hours > 0
					? `<span style="color: #6c757d;"> (${percentage}% ${__("от плана")})</span>`
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
		"Плановые данные определены на уровне:"
	)} ${frappe.utils.escape_html(result.plan_task_subject || "")}</div>`;
	const sources = result.plan_sources || [];
	if (sources.length) {
		html += `<div class="hours-note">${__("Источники плана:")}<ul>`;
		for (const source of sources) {
			html += `<li>${frappe.utils.escape_html(source.subject || "")} (${frappe.utils.escape_html(
				source.task_name || ""
			)}): ${source.planned_hours} ${__("ч.")}</li>`;
		}
		html += `</ul></div>`;
	}
	return html;
}

/** Plan/fact modal for a position row (demodev showTaskPlanFact). */
export async function showTaskPlanFact(frm, position) {
	if (!position?.document_name) {
		frappe.msgprint(__("Не выбрана задача для отображения информации"));
		return;
	}
	const message = await callLimits(getLimitsPayload(frm));
	const result = (message || []).find(
		(el) => String(el.position) === String(position.name || position.id)
	);
	if (!result) {
		frappe.msgprint(__("Нет данных плана/факта для позиции"));
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
		primary_action_label: __("Закрыть"),
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
					"Проект"
				)}: ${frappe.utils.escape_html(w.project)}, ${__("Роль")}: ${frappe.utils.escape_html(
					w.role
				)})<br>` +
				`&nbsp;&nbsp;${__("Фактические трудозатраты")}: ${
					w.completion_percentage
				}% ${__("плана")}`
		)
		.join("<br><br>");
	frappe.show_alert(
		{
			message: `<b>${__("Обратите внимание на следующие задачи:")}</b><br><br>${message}`,
			indicator: "yellow",
		},
		15
	);
}
