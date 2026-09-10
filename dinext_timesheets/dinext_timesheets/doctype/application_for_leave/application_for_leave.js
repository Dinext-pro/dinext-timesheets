// Copyright (c) 2026, Dinext and contributors
// For license information, please see license.txt

frappe.ui.form.on("Application For Leave", {
	alto_date(frm) {
		if (
			frm.doc.alfrom_date &&
			frm.doc.alto_date &&
			frappe.datetime.get_day_diff(frm.doc.alfrom_date, frm.doc.alto_date) > 0
		) {
			frappe.show_alert({
				message: __("End date cannot be earlier than start date."),
				indicator: "orange",
			});
			frm.set_value("alto_date", frm.doc.alfrom_date);
		}
	},
});
