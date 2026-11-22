/**
 * Manual New User Timesheet validate (demodev V10).
 * Fills period from Worker template, overlap check, dispatch date.
 */

const CONTEXT = "dinext_timesheets.dinext_timesheets.user_timesheet.api.get_timesheet_context";

/** Prefill owner on new form so validate does not fail on empty timesheet_from. */
export function applyNewTimesheetDefaults(frm) {
	if (!frm || !(frm.is_new() || frm.doc?.__islocal)) {
		return;
	}
	if (frm.doc.timesheet_from) {
		return;
	}
	frm.set_value("timesheet_from", frappe.session.user);
}

/**
 * @returns {Promise<boolean>} true if validate may continue
 */
export async function validateNewTimesheet(frm) {
	if (!(frm.doc.ts_valid_from && frm.doc.timesheet_from)) {
		frappe.msgprint(__("Please fill in all required fields"));
		frappe.validated = false;
		return false;
	}

	const { template, end } = await frappe.xcall(CONTEXT, {
		worker: frm.doc.timesheet_from,
		start: frm.doc.ts_valid_from,
	});
	frm.doc.ts_from_template = template.name;
	frm.doc.reporting_period = template.ttreporting_period;
	frm.doc.ts_valid_for = end;

	frm.refresh_field?.("ts_valid_for");
	frm.refresh_field?.("ts_from_template");
	frm.refresh_field?.("reporting_period");
	return true;
}
