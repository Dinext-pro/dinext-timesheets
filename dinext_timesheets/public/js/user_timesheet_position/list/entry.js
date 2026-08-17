/**
 * User Timesheet Position List entry (doctype_list_js).
 * Load order matches demodev CS deps: style → period → functions → history → listview.
 * ISS-2026-00926 phase 3.
 */
frappe.require(
	[
		"/assets/dinext_timesheets/js/user_timesheet_position/list/style.js",
		"/assets/dinext_timesheets/js/user_timesheet_position/list/period_filter.js",
		"/assets/dinext_timesheets/js/user_timesheet_position/list/functions.js",
		"/assets/dinext_timesheets/js/user_timesheet_position/list/history.js",
		"/assets/dinext_timesheets/js/user_timesheet_position/list/custom_listview.js",
	],
	() => {
		/* listview_settings applied by custom_listview.js */
	}
);
