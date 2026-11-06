/** Port from demodev Client Script User_Timesheet_Status_Color.js — ISS-2026-00926 phase 3 */
frappe.listview_settings['User Timesheet'] = {
    hide_name_column: true,
    hide_name_filter: true,
    add_fields: ['ut_status'],
    get_indicator: function(doc) {
        const status_colors = {
          "Draft": "white",
          "Pending Approval": "blue",
          "Rejected": "red",
          "Rework": "grey",
          "Approved": "green",
        };
        return [__(doc.ut_status), status_colors[doc.ut_status], "ut_status,=,"+doc.ut_status ];
    },/**/
    //before_render() {
        //frappe.breadcrumbs.clear();
        //frappe.breadcrumbs.append_breadcrumb_element('../../../../app/мои-таймшиты', 'Мои таймшиты');
        //frappe.breadcrumbs.append_breadcrumb_element('../../../../app/user-timesheet', 'ТШ');
    //},
    onload: function(listview) {
        add_reprocces_button( listview );
        const route = frappe.get_route() || [];
        document.body.classList.toggle(
            "ut-hide-desk-sidebar",
            (route[0] === "Form" || route[0] === "List") && route[1] === "User Timesheet"
        );
        frappe.require(["/assets/dinext_timesheets/css/user-timesheet.css"]);
        if (!window._utSidebarRouteBound) {
            window._utSidebarRouteBound = true;
            $(document).on("page-change.utTimesheetSidebar", () => {
                const r = frappe.get_route() || [];
                const ut = (r[0] === "Form" || r[0] === "List") && r[1] === "User Timesheet";
                document.body.classList.toggle("ut-hide-desk-sidebar", ut);
            });
        }
    }
};
