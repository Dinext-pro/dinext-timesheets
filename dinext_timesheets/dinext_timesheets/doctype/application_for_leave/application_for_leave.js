// Copyright (c) 2026, Dinext and contributors
// For license information, please see license.txt

(function () {
	frappe.provide("dinext_timesheets.approvals");
	const approvals = dinext_timesheets.approvals;
	if (approvals.aflApprovalsInstalled) return;
	approvals.aflApprovalsInstalled = true;
	frappe.dinext?.registerWorkflowApprovalForm?.("Application For Leave");

	const validateLeaveDates = (frm) => {
		const start = frm.doc.alfrom_date;
		const end = frm.doc.alto_date;
		if (!start || !end) return;
		if (frappe.datetime.get_diff(end, start) < 0) {
			frappe.show_alert(
				{
					message: __("End date cannot be earlier than start date"),
					indicator: "orange",
				},
				5
			);
			frm.set_value("alto_date", start);
		}
	};

	frappe.ui.form.on("Application For Leave", {
		alfrom_date: validateLeaveDates,
		alto_date: validateLeaveDates,
		validate(frm) {
			const hours = [frm.doc.alfrom_hours, frm.doc.alto_hours];
			if (hours.some((value) => Number(String(value ?? "").replaceAll(",", "")) < 0)) {
				frappe.throw(__("Leave hours cannot be negative."));
			}
		},
	});
})();
