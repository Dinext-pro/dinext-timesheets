/**
 * User Timesheet Form entry (doctype_js).
 * Mirror WE: require bundle immediately, then catch-up mount + form handlers.
 * Local: form CS V10 + helpers disabled — only app bundle.
 */
async function loadAndMount(frm) {
	if (!frm || frm.doctype !== "User Timesheet") {
		return;
	}
	if (!window.UserTimesheet?.ensureMounted) {
		return;
	}
	try {
		await window.UserTimesheet.ensureMounted(frm);
		if (window.UserTimesheet.setupFormChrome) {
			await window.UserTimesheet.setupFormChrome(frm);
		}
	} catch (err) {
		console.error("[UserTimesheet] loadAndMount", err);
	}
}

frappe.require(
	[
		"/assets/dinext_timesheets/css/user-timesheet.css",
		"user-timesheet.bundle.js",
	],
	() => {
		if (!window.UserTimesheet?.ensureMounted) {
			console.error("[UserTimesheet] user-timesheet.bundle: API missing");
			return;
		}
		if (cur_frm?.doctype === "User Timesheet") {
			loadAndMount(cur_frm);
		}
	}
);

frappe.ui.form.on("User Timesheet", {
	refresh(frm) {
		if ((frm.is_new() || frm.doc?.__islocal) && !frm.doc.timesheet_from) {
			frm.set_value("timesheet_from", frappe.session.user);
		}
		if (window.UserTimesheet?.ensureMounted) {
			loadAndMount(frm);
			return;
		}
		frappe.require(
			[
				"/assets/dinext_timesheets/css/user-timesheet.css",
				"user-timesheet.bundle.js",
			],
			() => loadAndMount(frm)
		);
	},
	async validate(frm) {
		if (!window.UserTimesheet?.saveTimesheetPositions) {
			await new Promise((resolve) => {
				frappe.require(["user-timesheet.bundle.js"], resolve);
			});
		}
		if (frm.is_new() || frm.doc?.__islocal) {
			if (window.UserTimesheet?.validateNewTimesheet) {
				const ok = await window.UserTimesheet.validateNewTimesheet(frm);
				if (ok === false) {
					frappe.validated = false;
				}
			}
			return;
		}
		if (window.UserTimesheet?.saveTimesheetPositions) {
			const ok = await window.UserTimesheet.saveTimesheetPositions(frm);
			if (ok === false) {
				frappe.validated = false;
				return;
			}
		}
		if (frappe.validated !== false && window.UserTimesheet?.alertLimitWarnings) {
			window.UserTimesheet.alertLimitWarnings(frm);
		}
	},
});
