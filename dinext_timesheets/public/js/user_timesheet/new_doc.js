/**
 * Manual New User Timesheet validate (demodev V10).
 * Fills period from Worker template, overlap check, dispatch date.
 */

async function timesheetOverlaps(user, start, end) {
	const [atStart, atEnd] = await Promise.all([
		frappe.db.get_list("User Timesheet", {
			filters: [
				["timesheet_from", "=", user],
				["ts_valid_from", "<=", start],
				["ts_valid_for", ">=", start],
			],
			fields: ["name"],
			limit: 1,
		}),
		frappe.db.get_list("User Timesheet", {
			filters: [
				["timesheet_from", "=", user],
				["ts_valid_from", "<=", end],
				["ts_valid_for", ">=", end],
			],
			fields: ["name"],
			limit: 1,
		}),
	]);
	return !!(atStart?.length || atEnd?.length);
}

function applyTemplatePeriod(frm, templateDoc) {
	const start = frm.doc.ts_valid_from;
	const period = templateDoc.ttreporting_period;

	if (period === "Месячный") {
		frm.doc.ts_valid_for = moment(start).endOf("month").format("YYYY-MM-DD");
		return;
	}
	if (period === "Полумесячный") {
		frm.doc.ts_valid_for = frappe.datetime.add_days(start, 15);
		return;
	}
	if (period === "Недельный") {
		const eom = moment(start).endOf("month").format("YYYY-MM-DD");
		const eow = moment(start).endOf("isoWeek").format("YYYY-MM-DD");
		frm.doc.ts_valid_for =
			frappe.datetime.get_day_diff(eom, eow) < 0 ? eom : eow;
	}
}

/**
 * @returns {Promise<boolean>} true if validate may continue
 */
export async function validateNewTimesheet(frm) {
	if (!(frm.doc.ts_valid_from && frm.doc.timesheet_from)) {
		frappe.msgprint(__("Пожалуйста заполните все необходимые поля"));
		frappe.validated = false;
		return false;
	}

	const workerTpl = await frappe.db.get_value(
		"Worker",
		{ wuser: frm.doc.timesheet_from },
		"wtimesheet_template"
	);
	const templ = workerTpl?.message?.wtimesheet_template;
	if (!templ) {
		frappe.msgprint(__("У сотрудника не задан шаблон таймшита"));
		frappe.validated = false;
		return false;
	}

	const templateDoc = await frappe.db.get_doc("Timesheet Template", templ);
	if (!frm.doc.ts_from_template) {
		frm.doc.ts_from_template = templ;
	}
	if (templateDoc.ttreporting_period && !frm.doc.reporting_period) {
		frm.doc.reporting_period = templateDoc.ttreporting_period;
	}

	applyTemplatePeriod(frm, templateDoc);

	if (!frm.doc.ts_valid_for) {
		frappe.msgprint(__("Не удалось определить период таймшита по шаблону"));
		frappe.validated = false;
		return false;
	}

	const exists = await timesheetOverlaps(
		frm.doc.timesheet_from,
		frm.doc.ts_valid_from,
		frm.doc.ts_valid_for
	);
	if (exists) {
		frappe.msgprint(__("Уже есть ТШ пересекающийся с этими датами"));
		frappe.validated = false;
		return false;
	}

	const dispatchDays = flt(templateDoc.working_days) || 0;
	frm.doc.ts_date_of_dispatch = frappe.datetime.add_days(
		frm.doc.ts_valid_for,
		dispatchDays
	);

	frm.refresh_field?.("ts_valid_for");
	frm.refresh_field?.("ts_date_of_dispatch");
	frm.refresh_field?.("ts_from_template");
	frm.refresh_field?.("reporting_period");
	return true;
}
