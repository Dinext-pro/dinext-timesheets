frappe.ui.form.on("Timesheet Settings", {
	setup(frm) {
		const query = () => ({
			query: "dinext_timesheets.timesheet_settings.utp_state_query",
		});
		frm.set_query("position_status", "position_rules", query);
		frm.set_query("position_status", "parent_rules", query);
	},
	refresh(frm) {
		frappe.call({
			method: "dinext_timesheets.timesheet_settings.hidden_status_options",
			callback(response) {
				const options = (response.message || []).join("\n");
				frm.fields_dict.hidden_list_statuses.grid.update_docfield_property(
					"position_status",
					"options",
					options
				);
			},
		});
	},
});
