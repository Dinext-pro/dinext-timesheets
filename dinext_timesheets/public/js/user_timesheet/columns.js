import { canEdit, dayField, isHoliday } from "./model.js";
import { limitIconColor, showTaskPlanFact } from "./limits.js";
import { FIELD_PROJECT, FIELD_ROLE, FIELD_TASK } from "./editors/cascade-commit.js";
import { roleOptionsForRow } from "./catalog.js";
import { getCascadeColDefWidth } from "./column-layout.js";
import { invalidCellClassRules, invalidCellTooltipGetter } from "./invalid-cells.js";

function holidayHeaderClass(holidays, date) {
	return isHoliday(holidays, date) ? "ut-holiday-col" : "";
}

/** demodev Check Limits_V2 setButtonStyle + title tooltip; click → plan/fact. */
function limitIconRenderer(frm) {
	return function (params) {
		const row = params?.data;
		if (!row || row.rowType !== "position") {
			return "";
		}
		const status = row.limit_status || "";
		const wrap = document.createElement("button");
		wrap.type = "button";
		wrap.className = `btn btn-xs ut-info-btn${
			status ? ` ut-limit-${status}` : ""
		}`;
		wrap.title = row.limit_tooltip || __("Plan / Fact");
		const color = limitIconColor(status);
		if (color) {
			wrap.style.color = color;
			wrap.style.borderColor = color;
		}
		wrap.innerHTML = '<i class="fa fa-info-circle" aria-hidden="true"></i>';
		wrap.addEventListener("mousedown", (e) => e.stopPropagation());
		wrap.addEventListener("click", (e) => {
			e.stopPropagation();
			const pos = (frm.ts_positions || []).find(
				(p) => String(p.name) === String(row.id)
			);
			showTaskPlanFact(frm, pos || row);
		});
		return wrap;
	};
}

/** Day hours: empty → 0, garbage → previous, never negative. */
export function parseTimesheetHourCell(params) {
	const raw = params?.newValue;
	if (raw == null || String(raw).trim() === "") {
		return 0;
	}
	const parsed = typeof DinextTable?.parseLocaleNumber === "function"
		? DinextTable.parseLocaleNumber(raw)
		: flt(raw);
	if (parsed == null || !Number.isFinite(Number(parsed))) {
		return Math.max(flt(params?.oldValue) || 0, 0);
	}
	return Math.max(Number(parsed), 0);
}

function markSelectCellEditable(frm, wrap, row) {
	if (!canEdit(frm) || row?.rowType !== "position") {
		return;
	}
	wrap.classList.add("ut-select-cell--editable");
}

/** Cell label stays first. Approver names are an extra line, only when present. */
function withApproverTitle(text, row) {
	const names = row?.rowType === "position" ? row.approver_tooltip || "" : "";
	if (!names) {
		return text;
	}
	return text ? `${text}\n${names}` : names;
}

const PICKER_COL_DEF = {
	edit: false,
	suppressFillHandle: true,
};

function projectSelectRenderer(frm) {
	return function (params) {
		const row = params?.data || {};
		const wrap = document.createElement("div");
		wrap.className = "ut-select-cell";
		const text = row.project_label || "";
		wrap.textContent = text;
		wrap.title = withApproverTitle(text, row);
		markSelectCellEditable(frm, wrap, row);
		return wrap;
	};
}

function taskSelectRenderer(frm) {
	return function (params) {
		const row = params?.data || {};
		const wrap = document.createElement("div");
		wrap.className = "ut-select-cell";
		const text = row.document_label || "";
		wrap.title = withApproverTitle(text, row);
		wrap.textContent = text;
		markSelectCellEditable(frm, wrap, row);
		return wrap;
	};
}

function roleSelectRenderer(frm) {
	return function (params) {
		const row = params?.data || {};
		const wrap = document.createElement("div");
		wrap.className = "ut-select-cell";
		const text = row.project_role || "";
		wrap.textContent = text;
		wrap.title = withApproverTitle(text, row);
		markSelectCellEditable(frm, wrap, row);
		return wrap;
	};
}

export function getColumns(frm) {
	const state = frm.ut;
	const dates = state?.dates || [];
	const holidays = state?.holidays || [];
	const editable = canEdit(frm);

	const saved = frm.ut?._cascadeColWidths || {};
	const invalidRules = invalidCellClassRules(frm);
	const invalidTooltip = invalidCellTooltipGetter(frm);
	const dayRules = {
		...invalidRules,
		"ut-leave-hours": (params) =>
			params?.data?.rowType === "leave" && flt(params.value) > 0,
		"project-budget-cell--zero": (params) => !(flt(params.value) > 0),
	};
	const totalRules = {
		...invalidRules,
		"project-budget-cell--zero": (params) => !(flt(params.value) > 0),
	};

	/** @type {import("dinext_common/table").DinextTableColumn[]} */
	const cols = [
		{
			field: "project_label",
			headerName: __("Project"),
			pinned: "left",
			width: saved[FIELD_PROJECT] || getCascadeColDefWidth(FIELD_PROJECT),
			minWidth: getCascadeColDefWidth(FIELD_PROJECT),
			...PICKER_COL_DEF,
			headerClass: "dinext-table-header--align-center",
			cellClassRules: invalidRules,
			tooltipValueGetter: invalidTooltip,
			cellRenderer: projectSelectRenderer(frm),
		},
		{
			field: "document_label",
			headerName: __("Task"),
			pinned: "left",
			width: saved[FIELD_TASK] || getCascadeColDefWidth(FIELD_TASK),
			minWidth: getCascadeColDefWidth(FIELD_TASK),
			...PICKER_COL_DEF,
			headerClass: "dinext-table-header--align-center",
			cellClassRules: invalidRules,
			tooltipValueGetter: invalidTooltip,
			cellRenderer: taskSelectRenderer(frm),
		},
		{
			field: "project_role",
			headerName: __("Project Role"),
			pinned: "left",
			type: "select",
			width: saved[FIELD_ROLE] || getCascadeColDefWidth(FIELD_ROLE),
			minWidth: getCascadeColDefWidth(FIELD_ROLE),
			edit: (row) => editable && row?.rowType === "position",
			cellEditor:
				typeof DinextTable !== "undefined"
					? DinextTable.SelectCellEditor
					: undefined,
			cellEditorParams: {
				frm,
				values: (params) => roleOptionsForRow(frm, params?.data),
			},
			headerClass: "dinext-table-header--align-center",
			cellClassRules: invalidRules,
			tooltipValueGetter: invalidTooltip,
			cellRenderer: roleSelectRenderer(frm),
		},
		{
			field: "limit_icon",
			headerName: "",
			pinned: "left",
			width: 30,
			minWidth: 30,
			maxWidth: 30,
			resizable: false,
			suppressSizeToFit: true,
			edit: false,
			cellClass: "ut-info-cell",
			headerClass: "ut-info-cell",
			cellRenderer: limitIconRenderer(frm),
		},
	];

	for (const date of dates) {
		const holiday = holidayHeaderClass(holidays, date);
		cols.push({
			field: dayField(date),
			headerName: moment(date).format("DD.MM"),
			type: "number",
			edit: (row) => editable && row?.rowType === "position",
			valueParser: parseTimesheetHourCell,
			width: 54,
			minWidth: 54,
			maxWidth: 54,
			resizable: false,
			suppressSizeToFit: true,
			cellClassRules: dayRules,
			tooltipValueGetter: invalidTooltip,
			/* Override number type align-right → center. */
			cellClass: ["dinext-table-cell--align-center", "ut-num-col", holiday]
				.filter(Boolean)
				.join(" "),
			headerClass: ["dinext-table-header--align-center", "ut-num-col", holiday]
				.filter(Boolean)
				.join(" "),
		});
	}

	cols.push({
		field: "total",
		headerName: __("Total"),
		type: "number",
		edit: false,
		width: 72,
		minWidth: 72,
		maxWidth: 72,
		resizable: false,
		suppressSizeToFit: true,
		pinned: "right",
		cellClassRules: totalRules,
		tooltipValueGetter: invalidTooltip,
		cellClass: "dinext-table-cell--align-center ut-num-col",
		headerClass: "dinext-table-header--align-center ut-num-col",
	});

	return cols;
}
