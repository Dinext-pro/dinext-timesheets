frappe.query_reports["Отчет по ТШ"] = {
    "onload": function(report) {
        // Принудительно инициализируем фильтр, если он пустой
        report.page.fields_dict.project.set_input("");
    },
    "filters": [
        {
            "fieldname": "project",
            "label": __("Проект"),
            "fieldtype": "Link",
            "options": "Project",
            "reqd": 0,
            "default": null,
            "always_pass": true
        },
        {
            "fieldname": "custom_username",
            "label": __("Пользователь"),
            "fieldtype": "Data",
            "reqd": 0,
            "default": null,
            "always_pass": true
        },
        {
            "fieldname": "user_group",
            "label": __("Функциональная группа"),
            "fieldtype": "Link",
            "options": "User Group",
            "reqd": 0,
            "default": null,
            "always_pass": true
        },
        {
            "fieldname": "from_date",
            "label": __("From Date"),
            "fieldtype": "Date",
            "reqd": 0,
            "default": null,
            "always_pass": true
        },
        {
            "fieldname": "to_date",
            "label": __("To Date"),
            "fieldtype": "Date",
            "reqd": 0,
            "default": null,
            "always_pass": true
        }
    ]
};
