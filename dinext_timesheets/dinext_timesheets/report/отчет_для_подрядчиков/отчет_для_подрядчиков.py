import frappe
from frappe import _

def execute(filters=None):
    columns = [
    #    {"fieldname": "user_email", "label": _("Email"), "fieldtype": "Data", "width": 180},
        {"fieldname": "user_name", "label": _("Пользователь"), "fieldtype": "Data", "width": 150},
        {"fieldname": "status", "label": _("Статус"), "fieldtype": "Data", "width": 100},
        {"fieldname": "project_id", "label": _("Проект (ID)"), "fieldtype": "Link", "options": "Project", "width": 150},
        {"fieldname": "project_name", "label": _("Наименование проекта"), "fieldtype": "Data", "width": 200},
        {"fieldname": "project_role", "label": _("Проектная роль"), "fieldtype": "Data", "width": 150},
        {"fieldname": "task_id", "label": _("Задача (ID)"), "fieldtype": "Link", "options": "Task", "width": 150},
        {"fieldname": "task_name", "label": _("Наименование задачи"), "fieldtype": "Data", "width": 200},
        {"fieldname": "date", "label": _("Дата"), "fieldtype": "Date", "width": 100},
        {"fieldname": "hours", "label": _("Часы"), "fieldtype": "Float", "width": 80},
        {"fieldname": "description", "label": _("Описание"), "fieldtype": "Data", "width": 300}
    ]

    query = """
        SELECT 
            p.user AS user_email,
            tu.full_name AS user_name,
            p.status AS status,
            p.project AS project_id,
            pr.project_name AS project_name,
            p.project_role AS project_role,
            p.document_name AS task_id,
            t.subject AS task_name,
            d.date AS date,
            d.hours AS hours,
            d.description AS description
        FROM 
             `tabUser` tu
        LEFT JOIN 
            `tabUser Timesheet Position` p ON p.`user` = tu.name 
        LEFT JOIN 
            `tabUser Timesheet Position Details` d ON d.parent = p.name
        LEFT JOIN 
            `tabProject` pr ON pr.name = p.project
        LEFT JOIN 
            `tabTask` t ON t.name = p.document_name
        WHERE 
            p.document_type = 'Task'
          # AND tu.name = %(user)
         
    """

    filters = filters or {}
    filter_conditions = []

    # Фильтр по пользователю (обязательный)
    if filters.get("user"):
        filter_conditions.append(f"p.user = '{filters.get('user')}'")

    # Остальные фильтры
    if filters.get("project"):
        filter_conditions.append(f"p.project = '{filters.get('project')}'")

    if filters.get("from_date") and filters.get("to_date"):
        filter_conditions.append(f"d.date BETWEEN '{filters.get('from_date')}' AND '{filters.get('to_date')}'")
    elif filters.get("from_date"):
        filter_conditions.append(f"d.date >= '{filters.get('from_date')}'")
    elif filters.get("to_date"):
        filter_conditions.append(f"d.date <= '{filters.get('to_date')}'")

    if filter_conditions:
        query += " AND " + " AND ".join(filter_conditions)

    data = frappe.db.sql(query, as_dict=True)

    return columns, data