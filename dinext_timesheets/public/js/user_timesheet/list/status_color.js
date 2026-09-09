/** Port from demodev Client Script User_Timesheet_Status_Color.js — ISS-2026-00926 phase 3 */
frappe.listview_settings['User Timesheet'] = {
    hide_name_column: true,
    hide_name_filter: true,
    add_fields: ['ut_status'],
    get_indicator: function(doc) {
        const status_colors = {
          "Черновик": "white",
          "На согласовании": "blue",
          "Отклонено": "red",
          "На доработке": "grey",
          "Согласован": "green",
        };
        return [(doc.ut_status), status_colors[doc.ut_status], "ut_status,=,"+doc.ut_status ];
    },/**/
    //before_render() {
        //frappe.breadcrumbs.clear();
        //frappe.breadcrumbs.append_breadcrumb_element('../../../../app/мои-таймшиты', 'Мои таймшиты');
        //frappe.breadcrumbs.append_breadcrumb_element('../../../../app/user-timesheet', 'ТШ');
    //},
    onload: function(listview) {
        add_reprocces_button( listview );
        document.body.classList.add("ut-hide-desk-sidebar");
        frappe.require(["/assets/dinext_timesheets/css/user-timesheet.css"]);
        if (!window._utSidebarRouteBound) {
            window._utSidebarRouteBound = true;
            frappe.router.on("change", () => {
                const r = frappe.get_route() || [];
                const ut = (r[0] === "Form" || r[0] === "List") && r[1] === "User Timesheet";
                if (!ut) {
                    document.body.classList.remove("ut-hide-desk-sidebar");
                }
            });
        }
    }
};
