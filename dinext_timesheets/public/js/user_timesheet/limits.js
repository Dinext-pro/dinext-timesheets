/**
 * Plan/fact limits (demodev Check Limits_V2 + Show Plan-Actual Data_V2).
 * Single path: PWA whitelist only. No SS / bare-method fallback.
 */
import { isTaskPickerOpen } from "./editors/task-picker-modal.js";
const LIMITS_METHOD = "project_workload_assignment.api.calculate_user_timesheet_limits";

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
				custom_username: pos.custom_username || frm.doc.timesheet_from_name || "",
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
	return (message || []).filter((r) => r.status === "block" || r.status === "warning");
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
				custom_username: p.custom_username || frm.doc.timesheet_from_name || "",
				details: (p.details || [])
					.filter((d) => d && d.date)
					.map((d) => ({ date: d.date, hours: flt(d.hours) })),
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
			error?.message || error?.exc || error?.responseJSON?.exception || String(error);
		errors.push(`${__("Error checking planned work efforts and limits")}: ${detail}`);
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
	/* Whole-row redraw remounts active cell editors and picker anchors. */
	if (
		!isTaskPickerOpen() &&
		!api.getEditingCells?.().length &&
		changedNodes.length &&
		api.redrawRows
	) {
		api.redrawRows({ rowNodes: changedNodes });
	}
}

/** Apply limit status onto position rows + refresh grid. */
export async function refreshLimits(frm) {
	if (!frm.ts_positions?.length || !frm.doc.name || !frm.ut?.table) {
		return;
	}
	const state = frm.ut;
	const generation = (state._limitsGeneration || 0) + 1;
	state._limitsGeneration = generation;
	let finishInflight = () => {};
	const done = new Promise((resolve) => {
		finishInflight = resolve;
	});
	frm.ut._limitsInflight = done;
	try {
		const message = await callLimits(getLimitsPayload(frm));
		if (frm.ut === state && state._limitsGeneration === generation) {
			applyLimitStyles(frm, message);
		}
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

function limitResultFor(frm, position) {
	const key = String(position?.name || position?.id || "");
	if (!key) {
		return null;
	}
	return frm.ut?.limitResults?.[key] || null;
}

/** Open common details using the current timesheet overlay. */
export async function showTaskPlanFact(frm, position) {
	if (!position?.document_name) {
		frappe.msgprint(__("No task selected to display information"));
		return;
	}
	if (frm.ut?._limitsTimer) {
		clearTimeout(frm.ut._limitsTimer);
		frm.ut._limitsTimer = null;
		await refreshLimits(frm);
	}
	if (frm.ut?._limitsInflight) await frm.ut._limitsInflight;
	let result = limitResultFor(frm, position);
	if (!result) {
		if (!frm.ut._limitDialogInflight) {
			frm.ut._limitDialogInflight = callLimits(getLimitsPayload(frm))
				.then((message) => {
					applyLimitStyles(frm, message);
					return message;
				})
				.finally(() => {
					if (frm.ut) frm.ut._limitDialogInflight = null;
				});
		}
		await frm.ut._limitDialogInflight;
		result = limitResultFor(frm, position);
	}
	if (!result) {
		frappe.msgprint(__("No plan/fact data for the position"));
		return;
	}
	await frappe.require("/assets/project_workload_assignment/js/limits/plan_fact.js");
	return project_workload_assignment.plan_fact_details.show({
		results: [result],
		title: result.task_subject || position.document_name,
		ownerName: frm.doc.timesheet_from_name,
	});
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
				)}: ${frappe.utils.escape_html(w.project)}, ${__(
					"Role"
				)}: ${frappe.utils.escape_html(w.role)})<br>` +
				`&nbsp;&nbsp;${__("Fact work efforts")}: ${w.completion_percentage}% ${__(
					"of plan"
				)}`
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
