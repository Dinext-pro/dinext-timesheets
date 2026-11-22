(function () {
	frappe.ui.form.on("User Timesheet Position", {
		onload(frm) {
			if (frm.is_new() || !frm.doc.user_timesheet) return;
			frappe.set_route("Form", "User Timesheet", frm.doc.user_timesheet);
		},
	});
})();
