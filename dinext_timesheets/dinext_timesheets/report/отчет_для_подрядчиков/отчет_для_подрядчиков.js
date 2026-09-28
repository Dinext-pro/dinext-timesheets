// Copyright (c) 2025, Dinord and contributors
// For license information, please see license.txt

frappe.query_reports["Отчет для Подрядчиков"] = {
    "onload": function(report) {
       // Устанавливаем текущего пользователя в фильтр
        report.set_filter_value('user', frappe.session.user);
        
        // Блокируем поле от редактирования
        const user_field = report.page.fields_dict.user;
        if (user_field) {
            user_field.set_value(frappe.session.user);
            user_field.$input.prop('disabled', true);
        }
                
        // Инициализация фильтра проекта
        report.page.fields_dict.project.set_input("");
    },
    "filters": [
        {
            "fieldname": "user",
            "label": ("Email"),
            "fieldtype": "Link",
            "options": "User",
            "reqd": 0,
            "hidden": 1,  // Скрываем, так как значение устанавливается автоматически
            "always_pass": true
        },
        {
            "fieldname": "project",
            "label": ("Проект"),
            "fieldtype": "Link",
            "options": "Project",
            "reqd": 0,
            "default": null,
            "always_pass": true
        },
        {
            "fieldname": "from_date",
            "label": ("From Date"),
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

