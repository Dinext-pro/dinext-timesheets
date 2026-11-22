// Copyright (c) 2026, Dinext and contributors
// For license information, please see license.txt

frappe.query_reports["Timesheet Deadline Discipline"] = {
    filters: [
        {fieldname:"from_date",label:__("From Date"),fieldtype:"Date",default:frappe.datetime.add_days(frappe.datetime.get_today(),-29),reqd:1},
        {fieldname:"to_date",label:__("To Date"),fieldtype:"Date",default:frappe.datetime.get_today(),reqd:1},
        {fieldname:"author",label:__("Author"),fieldtype:"Link",options:"User"},
        {fieldname:"timesheet",label:__("Timesheet"),fieldtype:"Link",options:"User Timesheet"},
        {fieldname:"approver",label:__("Approver"),fieldtype:"Link",options:"User"},
        {fieldname:"chart_metric",label:__("Chart Metric"),fieldtype:"Select",options:[{label:__("Submission"),value:"Submission"},{label:__("Approval"),value:"Approval"}],default:"Approval"},
    ],
};
