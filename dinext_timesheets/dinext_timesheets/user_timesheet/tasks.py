"""get_timesheet_tasks domain (port of demodev SS UT Get Task List)."""

from __future__ import annotations

import frappe
from frappe import _


# https://erp.dinord.ru/app/issue/ISS-2025-01094
# Назначение: вернуть список проектов (по клиентам) и доступных в них задач/запросов
# Входные параметры:
#   template_name: name (ID) Timesheet Template
#   ts_start, ts_end: строковые даты (YYYY-MM-DD или другие, поддерживаемые getdate)
#   ts_owner: user (email/ID)
#
# Результат: список словарей [{ "Клиент": [ { project info + tasks/issues }, ... ] }, ... ]

def load_projects_remap2_customers(template_name, ts_start, ts_end, ts_owner):
    """
    Возвращает проекты, сгруппированные по клиентам, с задачами (Task) и запросами (Issue),
    доступными пользователю ts_owner и включёнными в шаблон template_name.
    """
    # --- Валидация входных параметров (минимальная) ---
    if not ts_owner:
        frappe.throw(_("Missing ts_owner"))
    try:
        start_date = frappe.utils.getdate(ts_start)
        end_date = frappe.utils.getdate(ts_end)
    except Exception:
        frappe.throw(_("Invalid date format for ts_start/ts_end"))

    # --- Получаем шаблон и набор Doctype'ов, которые нам нужны (Task / Issue) ---
    template_doc = None
    try:
        template_doc = frappe.get_doc("Timesheet Template", template_name)
    except Exception:
        # если шаблон не найден — рассматриваем как пустой шаблон
        template_doc = None

    template_doctypes = []
    if template_doc and template_doc.get( "doctype_for_timesheet", None):
        # ожидаем, что list содержит объекты с полем dtdoctype
        template_doctypes = [d.dtdoctype for d in template_doc.doctype_for_timesheet if d.get("dtdoctype", None)]

    # --- Получаем user groups и роли пользователя ---
    # user groups: через User Group Member
    user_groups = [r.parent for r in frappe.get_all("User Group Member", filters={"user": ts_owner}, fields=["parent"])]
    # user roles: через User.roles (get_doc быстрее даёт актуальные роли)
    user_doc = frappe.get_doc("User", ts_owner)
    user_roles = [r.role for r in user_doc.get("roles", [])]

    # Уникальный набор возможных "участников" который мы используем для фильтрации Project Team Details
    participant_values = set([ts_owner] + user_groups + user_roles)
    #log( "participant_values: " + frappe.utils.cstr(participant_values))

    # --- Получаем строки Project Team Details, где участник совпадает с пользователем/группой/ролями ---
    # Мы получаем только те строки, где pt_participant совпадает с одним из participant_values.
    # Дальше — фильтрация по датам и статусу проекта производится в Python (чтобы избежать сложных SQL)
    if not participant_values:
        # Если совсем пусто — нет смысла продолжать
        return []

    team_rows = frappe.get_all(
        "Project Team Details",
        filters=[["pt_participant", "in", list(participant_values)]],
        fields=["parent as project", "pt_role", "pt_participant", "pt_participant_type", "pt_valid_from", "pt_valid_for"]
    )

    # Если нет совпадений в команде — возвращаем пустой список
    if not team_rows:
        return []

    # --- Список уникальных проектов из team_rows ---
    project_names = list({r.project for r in team_rows if r.project})

    if not project_names:
        return []

    # --- Загружаем проекты — применяем основные фильтры (Open, is_active = Yes) ---
    # Также можно дополнительно фильтровать по expected dates, но удобнее сделать проверку в Python
    projects = frappe.get_all(
        "Project",
        filters=[
            ["name", "in", project_names],
            ["status", "=", "Open"],
            ["is_active", "=", "Yes"]
        ],
        fields=["name", "customer", "project_name", "expected_start_date", "expected_end_date"]
    )

    if not projects:
        return []

    # Преобразуем в dict для быстрого доступа
    projects_by_name = {p.name: p for p in projects}

    # --- Для каждого проекта аггрегируем роли (pt_role) из team_rows и фильтруем строки по датам ---
    # Правило дат:
    #  - Если pt_valid_for задан: считаем что строка применима, если интервал [pt_valid_from, pt_valid_for] пересекается с [start_date, end_date]
    #  - Если pt_valid_for не задан: используем даты проекта expected_start/end и проверяем пересечение с [start_date, end_date]

    def dates_overlap(a_start, a_end, b_start, b_end):
        return (a_start <= b_end) and (b_start <= a_end)

    project_roles_map = {}  # project -> set(roles)
    valid_projects = set()  # проекты, где нашёлся валидный team row по датам

    for row in team_rows:
        proj = row.project
        if proj not in projects_by_name:
            # проект либо закрыт/неактивен либо отсутствует — пропускаем
            continue

        # вычисляем период применения строки team row
        if row.pt_valid_from and row.pt_valid_for:
            try:
                r_start = frappe.utils.getdate(row.pt_valid_from)
                r_end = frappe.utils.getdate(row.pt_valid_for)
            except Exception:
                # если некорректные даты — пропускаем строку
                continue
        else:
            # используем даты проекта как период применения
            proj_doc = projects_by_name.get(proj)
            # Если у проекта нет дат — считаем, что строка действительна глобально
            if not proj_doc.expected_start_date or not proj_doc.expected_end_date:
                r_start = start_date
                r_end = end_date
            else:
                r_start = frappe.utils.getdate(proj_doc.expected_start_date)
                r_end = frappe.utils.getdate(proj_doc.expected_end_date)

        # проверяем пересечение периодов строки и требуемого периода ts_start..ts_end
        if dates_overlap(r_start, r_end, start_date, end_date):
            # строка считается валидной — добавляем роль проекта
            project_roles_map.setdefault(proj, set())
            if row.pt_role:
                project_roles_map[proj].add(row.pt_role)
            else:
                # если pt_role отсутствует — можно добавить тип/участника для информации
                project_roles_map[proj].add(row.pt_participant or "participant")

            valid_projects.add(proj)

    # Отфильтруем проекты только с валидными team rows
    projects_filtered = [projects_by_name[p] for p in valid_projects if p in projects_by_name]
    #log( "projects_filtered: " + frappe.utils.cstr(projects_filtered))
    if not projects_filtered:
        return []

    # --- Получаем доступные для пользователя ToDo и DocShare (видимые задачи/запросы) ---
    # Используем frappe.get_all для переносимости
    todo_items = frappe.get_all(
        "ToDo",
        filters={
            "allocated_to": ts_owner,
            "status": "Open",
            "reference_type": ["in", ["Task", "Issue"]]
        },
        fields=["reference_name", "reference_type"]
    )

    docshare_items = frappe.get_all(
        "DocShare",
        filters={
            "user": ts_owner,
            "read": 1,
            "share_doctype": ["in", ["Task", "Issue"]]
        },
        fields=["share_name", "share_doctype"]
    )

    #visible_tasks = {t.reference_name for t in todo_items if t.reference_type == "Task"} | \
    #                {d.share_name for d in docshare_items if d.share_doctype == "Task"}
    #visible_issues = {t.reference_name for t in todo_items if t.reference_type == "Issue"} | \
    #                 {d.share_name for d in docshare_items if d.share_doctype == "Issue"}
                     
    visible_tasks = set([t["reference_name"] for t in todo_items if t.get("reference_type") == "Task"]) | \
                    set([d["share_name"] for d in docshare_items if d.get("share_doctype") == "Task"])
    visible_issues = set([t["reference_name"] for t in todo_items if t.get("reference_type") == "Issue"]) | \
                     set([d["share_name"] for d in docshare_items if d.get("share_doctype") == "Issue"])
                     
    #log( "visible_tasks: " + frappe.utils.cstr(visible_tasks))
    #log( "visible_issues: " + frappe.utils.cstr(visible_issues))

    # --- Получаем задачи и запросы (Task / Issue) — только для отфильтрованных проектов и видимых айтемов ---
    proj_names_list = [p.name for p in projects_filtered]

    tasks_response = []
    if "Task" in template_doctypes and proj_names_list and visible_tasks:
        # Используем get_all с фильтрами; передаём списки как Python list
        tasks_response = frappe.get_all(
            "Task",
            fields=[
                "name", "subject", "project", "custom_include", "status", "completed_on",
                "closing_date", "exp_start_date", "act_start_date", "exp_end_date", "parent_task"
            ],
            filters=[
                ["project", "in", proj_names_list],
                ["name", "in", list(visible_tasks)],
                ["status", "not in", ["Cancelled", "Template"]],
                ["custom_include", "=", 1],
                ["is_milestone", "=", 0],
                ["exp_start_date", "<=", ts_end]
            ],
            limit=10000
        )

    issues_response = []
    if "Issue" in template_doctypes and proj_names_list and visible_issues:
        issues_response = frappe.get_all(
            "Issue",
            fields=[
                "name", "subject", "project", "custom_include", "status",
                "opening_date", "custom_expected_resolution_date", "resolution_date"
            ],
            filters=[
                ["project", "in", proj_names_list],
                ["name", "in", list(visible_issues)],
                ["custom_include", "=", 1]
            ],
            limit=10000
        )

    # --- Сбор в карты: project -> list(items) ---
    tasks_map = {}
    for t in tasks_response:
        proj = t.get("project")
        if not proj:
            continue

        # проверяем актуальность по правилам
        valid = False
        if t.get("status") != "Completed":
            if t.get("exp_start_date") and t.get("exp_end_date"):
                try:
                    if frappe.utils.getdate(t["exp_end_date"]) >= start_date:
                        valid = True
                except Exception:
                    pass
        else:
            if t.get("completed_on"):
                try:
                    if frappe.utils.getdate(t["completed_on"]) >= start_date:
                        valid = True
                except Exception:
                    pass

        if valid:
            tasks_map.setdefault(proj, []).append({
                "name": t.get("name"),
                "subject": t.get("subject"),
                "parent_task": t.get("parent_task"),
                "included": t.get("custom_include"),
                "tsdoctype": "Task",
                "project": proj,
                "status": t.get("status")
            })

    issues_map = {}
    for i in issues_response:
        proj = i.get("project")
        if not proj:
            continue
        issues_map.setdefault(proj, []).append({
            "name": i.get("name"),
            "subject": i.get("subject"),
            "included": i.get("custom_include"),
            "tsdoctype": "Issue",
            "project": proj
        })

    #log( "tasks_map: " + frappe.utils.cstr(tasks_map))
    #log( "issues_map: " + frappe.utils.cstr(issues_map))

    # --- Построение иерархии задач (уровней) по проектам ---
    # Алгоритм: для каждого проекта строим словарь задач, строим children map и BFS от корней
    structured_tasks_by_project = {}

    for proj in proj_names_list:
        proj_tasks = tasks_map.get(proj, [])
        if not proj_tasks:
            # нет задач — можно пропустить (в финале будут только проекты с задачами/запросами)
            continue

        # lookup по имени
        lookup = {t["name"]: dict(t, level=None) for t in proj_tasks if t.get("name")}
        #log( "lookup: " + frappe.utils.cstr(lookup))
        # children map
        children = {}
        for t in proj_tasks:
            parent = t.get("parent_task")
            if parent and parent in lookup:
                children.setdefault(parent, []).append(t["name"])
            else:
                # parent отсутствует или не в наборе — это root candidate
                pass

        queue = []
        idx = 0  # индекс текущего головы очереди
        # инициализируем корни
        for name, node in lookup.items():
            parent = node.get("parent_task")
            if not parent or parent not in lookup:
                node["level"] = 0
                queue.append(name)

        # BFS через list + index
        max_iterations = 100000  # guard на случай циклов
        iterations = 0
        while idx < len(queue) and iterations < max_iterations:
            iterations = iterations + 1
            cur = queue[idx]
            idx = idx + 1
            cur_level = lookup[cur]["level"]
            for child in children.get(cur, []):
                if lookup[child]["level"] is None or lookup[child]["level"] > cur_level + 1:
                    lookup[child]["level"] = cur_level + 1
                    queue.append(child)
        # оставшиеся None помечаем как -1 (возможный цикл или несвязанная цепочка)
        for name, node in lookup.items():
            if node["level"] is None:
                # cycle / orphan — keep non-negative for UI indent (" ".repeat)
                node["level"] = 0

        # сохранение результатов
        structured_tasks_by_project[proj] = list(lookup.values())

    # --- Формирование окончательной структуры: клиенты -> проекты -> задачи/запросы ---
    organized_customers = {}
    for proj in projects_filtered:
        proj_name = proj.name
        customer_name = (proj.customer.strip() if proj.customer else _("Без Клиента"))
        # объединяем задачи и запросы
        items = []
        items.extend(structured_tasks_by_project.get(proj_name, []))
        items.extend(issues_map.get(proj_name, []))
        # только проекты с задачами/запросами и ролями
        roles = sorted(list(project_roles_map.get(proj_name, []))) if project_roles_map.get(proj_name) else []
        if items and roles:
            organized_customers.setdefault(customer_name, []).append({
                "project_name": proj.project_name,
                "name": proj_name,
                "roles": roles,
                "tasks_issues": items,
                "expected_start_date": proj.expected_start_date,
                "expected_end_date": proj.expected_end_date
            })

    # преобразуем в список словарей как в оригинале
    result = [{customer: projects} for customer, projects in organized_customers.items()]

    return result
