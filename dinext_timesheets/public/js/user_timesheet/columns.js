import { canEdit, dayField, isHoliday } from "./model.js";
import { limitIconColor, showTaskPlanFact } from "./limits.js";
import {
	FIELD_PROJECT,
	FIELD_ROLE,
	FIELD_TASK,
	openCascadeSelect,
} from "./editors/cascade-select.js";
import { getCascadeColDefWidth } from "./column-layout.js";
import { invalidCellClassRules } from "./invalid-cells.js";

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
		wrap.className = `btn btn-default btn-xs ut-info-btn${
			status ? ` ut-limit-${status}` : ""
		}`;
		wrap.title = row.limit_tooltip || __("План / факт");
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

function wireSelectCell(frm, wrap, row, params, field) {
	if (!canEdit(frm) || row?.rowType !== "position") {
		return;
	}
	wrap.classList.add("ut-select-cell--editable");
	/* mousedown + preventDefault: same click must not land on freshly mounted <select>
	 * (native open → blur → instant collapse). */
	wrap.addEventListener("mousedown", (ev) => {
		if (ev.button !== 0) {
			return;
		}
		ev.preventDefault();
		ev.stopPropagation();
		/* Always open list; deferActivate avoids same-pointer open→blur collapse. */
		openCascadeSelect(frm, {
			params,
			field,
			openList: true,
			deferActivate: true,
		});
	});
}

function projectSelectRenderer(frm) {
	return function (params) {
		const row = params?.data || {};
		const wrap = document.createElement("div");
		wrap.className = "ut-select-cell";
		const text = row.project_label || "";
		wrap.textContent = text;
		wrap.title = text;
		wireSelectCell(frm, wrap, row, params, FIELD_PROJECT);
		return wrap;
	};
}

function taskSelectRenderer(frm) {
	return function (params) {
		const row = params?.data || {};
		const wrap = document.createElement("div");
		wrap.className = "ut-select-cell";
		const text = row.document_label || "";
		if (row.rowType === "position" && row.status === "Отклонено" && row.reject_reason) {
			wrap.classList.add("ut-reject-label");
			wrap.title = row.reject_reason;
		} else {
			wrap.title = text;
		}
		wrap.textContent = text;
		wireSelectCell(frm, wrap, row, params, FIELD_TASK);
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
		wrap.title = text;
		wireSelectCell(frm, wrap, row, params, FIELD_ROLE);
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

	/** @type {import("dinext_common/table").DinextTableColumn[]} */
	const cols = [
		{
			field: "project_label",
			headerName: __("Проект"),
			pinned: "left",
			width: saved[FIELD_PROJECT] || getCascadeColDefWidth(FIELD_PROJECT),
			minWidth: 140,
			edit: false,
			cellClassRules: invalidRules,
			cellRenderer: projectSelectRenderer(frm),
		},
		{
			field: "document_label",
			headerName: __("Задача"),
			pinned: "left",
			width: saved[FIELD_TASK] || getCascadeColDefWidth(FIELD_TASK),
			minWidth: 160,
			edit: false,
			cellClassRules: invalidRules,
			cellRenderer: taskSelectRenderer(frm),
		},
		{
			field: "project_role",
			headerName: __("Проектная роль"),
			pinned: "left",
			width: saved[FIELD_ROLE] || getCascadeColDefWidth(FIELD_ROLE),
			minWidth: 120,
			edit: false,
			cellClassRules: invalidRules,
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
			width: 54,
			minWidth: 54,
			maxWidth: 54,
			resizable: false,
			suppressSizeToFit: true,
			cellClassRules: invalidRules,
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
		headerName: __("Итого"),
		type: "number",
		edit: false,
		width: 72,
		minWidth: 72,
		maxWidth: 72,
		resizable: false,
		suppressSizeToFit: true,
		pinned: "right",
		cellClassRules: invalidRules,
		cellClass: "dinext-table-cell--align-center ut-num-col",
		headerClass: "dinext-table-header--align-center ut-num-col",
	});

	return cols;
}
