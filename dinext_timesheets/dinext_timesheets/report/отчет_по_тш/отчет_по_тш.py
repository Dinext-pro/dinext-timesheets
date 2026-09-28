import frappe
from frappe import _


def execute(filters=None):
    # колонки
    columns = [
        {"fieldname": "user", "label": _("Пользователь"), "fieldtype": "Data", "width": 150},
        {"fieldname": "user_group", "label": _("Функциональная группа"), "fieldtype": "Link", "options": "User Group", "width": 150},
        {"fieldname": "status", "label": _("Статус"), "fieldtype": "Data", "width": 100},
        {"fieldname": "project_id", "label": _("Проект (ID)"), "fieldtype": "Link", "options": "Project", "width": 150},
        {"fieldname": "project_name", "label": _("Наименование проекта"), "fieldtype": "Data", "width": 200},
        {"fieldname": "project_role", "label": _("Проектная роль"), "fieldtype": "Data", "width": 150},
        {"fieldname": "task_id", "label": _("Задача (ID)"), "fieldtype": "Dynamic Link", "options": "document_type", "width": 150},
        {"fieldname": "task_name", "label": _("Наименование задачи"), "fieldtype": "Data", "width": 200},
        {"fieldname": "date", "label": _("Дата"), "fieldtype": "Date", "width": 100},
        {"fieldname": "hours", "label": _("Часы"), "fieldtype": "Float", "width": 80},
        {"fieldname": "description", "label": _("Описание"), "fieldtype": "Data", "width": 300}
    ]

    query = """
        SELECT 
            p.custom_username AS user,
            p.user_group AS user_group,
            p.status AS status,
            p.project AS project_id,
            pr.project_name AS project_name,
            p.project_role AS project_role,
            p.document_name AS task_id,
            CASE 
                WHEN p.document_type = 'Issue' THEN i.subject 
                WHEN p.document_type = 'Task' THEN t.subject 
                ELSE 'Неизвестный тип'
            END AS task_name,
            d.date AS date,
            d.hours AS hours,
            d.description AS description
        FROM 
            `tabUser Timesheet Position` p
        LEFT JOIN 
            `tabUser Timesheet Position Details` d ON d.parent = p.name
        LEFT JOIN 
            `tabProject` pr ON pr.name = p.project
        LEFT JOIN 
            `tabIssue` i ON p.document_type = 'Issue' AND i.name = p.document_name
        LEFT JOIN 
            `tabTask` t ON p.document_type = 'Task' AND t.name = p.document_name
    """

    # фильтры
    filters = filters or {}
    filter_conditions = []

    if filters.get("project"):
        filter_conditions.append(f"p.project = '{filters.get('project')}'")

    if filters.get("custom_username"):
        filter_conditions.append(f"p.custom_username = '{filters.get('custom_username')}'")

    if filters.get("user_group"):
        filter_conditions.append(f"p.user_group = '{filters.get('user_group')}'")

    if filters.get("from_date") and filters.get("to_date"):
        filter_conditions.append(f"d.date BETWEEN '{filters.get('from_date')}' AND '{filters.get('to_date')}'")
    elif filters.get("from_date"):
        filter_conditions.append(f"d.date >= '{filters.get('from_date')}'")
    elif filters.get("to_date"):
        filter_conditions.append(f"d.date <= '{filters.get('to_date')}'")

    # если есть условия, добавляем WHERE
    if filter_conditions:
        query += " WHERE " + " AND ".join(filter_conditions)

    data = frappe.db.sql(query, as_dict=True)

    return columns, data
