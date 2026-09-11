/**
 * User Timesheet List entry (doctype_list_js).
 * Port demodev: User_Timesheet_Status_Color + UT List Reprocess JE.
 * ISS-2026-00926 phase 3.
 */
frappe.require(
	[
		"/assets/dinext_timesheets/js/user_timesheet/list/status_color.js",
		"/assets/dinext_timesheets/js/user_timesheet/list/reprocess_je.js",
	],
	() => {
		/* listview_settings applied by status_color.js */
	}
);
