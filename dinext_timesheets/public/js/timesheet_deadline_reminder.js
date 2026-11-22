/** Scoped Task/Issue reminders. The server owns deadline and overdue rules. */
(() => {
	frappe.dinext = frappe.dinext || {};
	if (frappe.dinext.timesheetDeadlineReminder) return;
	const state = (frappe.dinext.timesheetDeadlineReminder = { pending: false, dialog: null });
	async function refresh() {
		if (!frappe.model.can_read("User Timesheet")) return;
		const owner = frappe.session.user;
		const key = `${window.location.host}:${owner}:timesheet-overdue-until`;
		if (state.pending || state.dialog?.$wrapper.is(":visible") || Number(localStorage.getItem(key) || 0) > Date.now()) return;
		state.pending = true;
		try {
			const summary = await frappe.xcall("dinext_timesheets.deadlines.get_my_overdue_summary");
			const route = frappe.get_route();
			if (!summary?.value || frappe.session.user !== owner || route[0] !== "Form" || !["Task", "Issue"].includes(route[1])) return;
			const dialog = new frappe.ui.Dialog({
				title: __("Overdue Timesheets"),
				fields: [{ fieldtype: "HTML", options: __("You have {0} overdue timesheets. Complete and submit them for approval.", [summary.value]) }],
				primary_action_label: __("Go to Timesheets"),
				primary_action() {
					dialog.hide();
					frappe.route_options = summary.route_options;
					frappe.set_route(summary.route);
				},
				secondary_action_label: __("Remind Me Later"),
				secondary_action() {
					localStorage.setItem(key, String(Date.now() + 30 * 60 * 1000));
					dialog.hide();
				},
			});
			state.dialog = dialog;
			dialog.show();
		} finally {
			state.pending = false;
		}
	}
	for (const doctype of ["Task", "Issue"]) frappe.ui.form.on(doctype, { refresh });
})();
