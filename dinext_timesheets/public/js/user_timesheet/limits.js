/**
 * Plan/fact limits (demodev Check Limits_V2 + Show Plan-Actual Data_V2).
 * Single path: PWA whitelist only. No SS / bare-method fallback.
 */
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
 * demodev apply_limit_styles: write status/tooltip onto rows, force AG Grid redraw.
 * Same rowData ref is ignored by AG Grid — replace rows + refreshCells/redrawRows.
 */
export function applyLimitStyles(frm, results) {
	const byPos = {};
	(results || []).forEach((r) => {
		byPos[String(r.position)] = r;
	});
	frm.ut.limitResults = byPos;

	const nextRows = (frm.ut.rows || []).map((row) => {
		if (row.rowType !== "position") {
			return row;
		}
		const r = byPos[String(row.id)];
		return {
			...row,
			limit_status: r?.status || "",
			limit_icon: r?.status || "",
			limit_tooltip: limitTooltipForResult(r),
		};
	});
	frm.ut.rows = nextRows;

	const table = frm.ut.table;
	if (!table) {
		return;
	}
	table.refresh?.(nextRows);
	const api = table.api;
	if (api?.refreshCells) {
		api.refreshCells({ columns: ["limit_icon"], force: true });
	}
	if (api?.redrawRows) {
		api.redrawRows();
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
		if (key === "users") {
			continue;
		}
		rows.push({
			status: key === "total" ? __("Всего") : key,
			isTotal: key === "total",
			plan: Number.parseFloat(result.planned_hours).toFixed(1),
			fact: `${Number.parseFloat(result.hours_data[key]).toFixed(1)} ч.`,
			percent: calculatePercentage(result.hours_data[key]),
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

function getParentTaskInfoHtml(result) {
	if (result.planned_hours > 0) {
		return `<div class="hours-note">${__(
			"Плановые данные определены на уровне:"
		)} ${frappe.utils.escape_html(result.plan_task_subject || "")}</div>`;
	}
	return "";
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
