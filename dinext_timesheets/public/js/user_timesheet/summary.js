import { dayField } from "./model.js";

/** Bottom summary: sum of day columns across all body rows. */
export function buildSummaryRows(frm) {
	const state = frm.ut;
	const dates = state?.dates || [];
	const rows = state?.rows || [];
	const summary = {
		id: "ut_day_totals",
		project_label: "",
		document_label: __("Итого"),
		project_role: "",
		total: 0,
	};

	for (const date of dates) {
		const field = dayField(date);
		let sum = 0;
		for (const row of rows) {
			if (row.rowType === "section") {
				continue;
			}
			sum += flt(row[field]) || 0;
		}
		summary[field] = sum;
		summary.total += sum;
	}

	return [summary];
}
