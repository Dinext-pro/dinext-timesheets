frappe.ui.form.on("Timesheet Settings", {
	setup(frm) {
		const query = () => ({
			query: "dinext_timesheets.timesheet_settings.utp_state_query",
		});
		frm.set_query("position_status", "position_rules", query);
		frm.set_query("position_status", "parent_rules", query);
	},
});
