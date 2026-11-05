# ruff: noqa: RUF001 -- Russian card names and stored workflow states are intentional.
"""Owned synthetic card fixtures. No accounting posting or external notifications."""

from __future__ import annotations

import json
from pathlib import Path

import frappe
from dinext_common.tests.ui_test_helpers import PASSWORD, _ensure_role, _ensure_user, _manual_task
from frappe.tests.ui_test_helpers import whitelist_for_tests
from frappe.utils import add_days, now_datetime

SOURCES = ("User Timesheet Position", "User Timesheet", "Application For Leave", "Expense Claim")
READ_TYPES = (
	*SOURCES,
	"Number Card",
	"Workspace",
	"Employee",
	"Worker",
	"Project",
	"Project Role",
	"Issue",
	"Report",
	"Kanban Board",
	"Timesheet Settings",
	"Support Settings",
)
VERSION = 6


def identity(namespace):
	if namespace not in {"test", "cypress", "demo"}:
		raise ValueError("Unknown fixture namespace")
	return f"NCQA-{namespace}-"


def guard():
	if frappe.local.site not in {"localhost", "test_site"} or frappe.session.user != "Administrator":
		raise frappe.PermissionError("Local test administrator required")
	if not (frappe.flags.in_test or getattr(frappe.local, "dev_server", False)):
		raise frappe.PermissionError("Development or test context required")


def state_path(namespace):
	identity(namespace)
	return Path(frappe.get_site_path("private", f"number-cards-{namespace}.json"))


def insert(dt, name, **values):
	# db_insert replaces an explicit owner when creation is missing.
	stamp = now_datetime()
	doc = frappe.get_doc(
		{
			"doctype": dt,
			"name": name,
			"creation": stamp,
			"modified": stamp,
			"owner": frappe.session.user,
			"modified_by": frappe.session.user,
			**values,
		}
	)
	doc.db_insert()
	return doc.name


def grant_read_permissions(role):
	for dt in READ_TYPES:
		# A first Custom DocPerm would suppress every standard role on this DocType.
		custom = frappe.db.exists("Custom DocPerm", {"parent": dt, "role": ["not like", "NCQA-%"]})
		kind = "Custom DocPerm" if custom else "DocPerm"
		if not frappe.db.exists(kind, {"parent": dt, "role": role, "permlevel": 0}):
			insert(
				kind,
				frappe.generate_hash(length=20),
				parent=dt,
				parenttype="DocType",
				parentfield="permissions",
				role=role,
				permlevel=0,
				read=1,
			)


def cleanup(namespace="cypress"):
	guard()
	prefix = identity(namespace)
	for dt in ("Available Workflow Transitions",):
		parents = frappe.get_all(
			"Workflow Task", filters={"source_title": ["like", prefix + "%"]}, pluck="name"
		)
		if parents:
			frappe.db.delete(dt, {"parent": ["in", parents]})
	frappe.db.delete("Workflow Task", {"source_title": ["like", prefix + "%"]})
	frappe.db.delete("Workflow Document State", {"parent": ["like", prefix + "%"]})
	frappe.db.delete("Workflow", {"name": ["like", prefix + "%"]})
	for dt in (*SOURCES, "Expense Claim Detail", "Issue", "Project", "Project Role", "Worker", "Employee"):
		frappe.db.delete(dt, {"name": ["like", prefix + "%"]})
	role = prefix + "Reader"
	frappe.db.delete("Custom DocPerm", {"role": role})
	frappe.db.delete("DocPerm", {"role": role})
	frappe.db.delete("DocType Permission Condition", {"role": role})
	for who in ("main", "other", "empty"):
		user = f"ncqa.{namespace}.{who}@example.invalid"
		for dt in ("Has Role", "User Email", "Block Module"):
			frappe.db.delete(dt, {"parent": user})
		frappe.db.delete("Notification Settings", {"name": user})
		if frappe.db.exists("User", user):
			frappe.delete_doc("User", user, ignore_permissions=True, force=True)
		frappe.clear_cache(user=user)
	frappe.db.delete("Role", {"name": role})
	state_path(namespace).unlink(missing_ok=True)
	frappe.clear_cache()
	return {"cleaned": namespace}


def seed(namespace="cypress"):
	guard()
	path = state_path(namespace)
	if path.exists():
		old = json.loads(path.read_text())
		if old.get("version") == VERSION and frappe.db.exists("User", old["user"]):
			return old
	cleanup(namespace)
	p = identity(namespace)
	role = p + "Reader"
	_ensure_role(role)
	users = {who: f"ncqa.{namespace}.{who}@example.invalid" for who in ("main", "other", "empty")}
	for who, email in users.items():
		_ensure_user(email, p + who, [role, "Desk User", "Dinext_Worker", "Dinext_UTP_Appoval"])
		frappe.db.set_value("User", email, "language", "en" if who == "other" else "ru")
	grant_read_permissions(role)
	# Scope the fixture role to owned sources in additional permission rules.
	for rule in frappe.get_all("DocType Permission", fields=["name", "ref_doctype"]):
		if rule.ref_doctype not in SOURCES:
			continue
		insert(
			"DocType Permission Condition",
			frappe.generate_hash(length=20),
			parent=rule.name,
			parenttype="DocType Permission",
			parentfield="conditions",
			role=role,
			perm_level="Full Access",
			script=f"conditions = \"`tab{rule.ref_doctype}`.`name` like '{p}%'\"",
		)
	frappe.cache.delete_value("doctype_permission_map")
	company = frappe.db.get_value("Company", {}, "name")
	for who in ("main", "other"):
		insert(
			"Employee",
			p + who,
			employee_name=p + who,
			first_name=p + who,
			user_id=users[who],
			company=company,
			status="Active",
			date_of_joining="2020-01-01",
		)
		insert("Worker", p + who, wuser=users[who], wfullname=p + who, wvalid_from="2020-01-01")
	insert("Project", p + "Project", project_name=p + "Project", status="Open")
	insert("Project Role", p + "Role")
	created = []

	def source(dt, suffix, **values):
		name = insert(dt, p + suffix, owner=users["main"], **values)
		created.append((dt, name))
		return name

	ut = {}
	for i, status in enumerate(("Draft", "Rework", "Pending Approval", "Rejected", "Approved")):
		ut[status] = source(
			"User Timesheet",
			"UT-" + status,
			timesheet_from=users["main"],
			timesheet_from_name=p + "main",
			ts_valid_from=add_days("2026-01-01", i * 7),
			ts_valid_for=add_days("2026-01-07", i * 7),
			ut_status=status,
			ts_date_of_dispatch=add_days(now_datetime(), -1 if status in {"Draft", "Rejected"} else 2),
			is_overdue=int(status in {"Draft", "Rejected"}),
		)
	legacy = [
		source(
			"User Timesheet",
			f"UT-legacy-{i}",
			timesheet_from=users["main"],
			ts_valid_from="2026-08-01",
			ut_status=status,
		)
		for i, status in enumerate((None, "", "Черновик", "На доработке"))
	]
	other_timesheet = source(
		"User Timesheet",
		"UT-other",
		timesheet_from=users["other"],
		ts_valid_from="2026-03-01",
		ut_status="Pending Approval",
	)
	leaves = {}
	for status in ("Редактирование", "На согласовании", "Согласовано", "Отклонено"):
		leaves[status] = source(
			"Application For Leave",
			"AFL-" + status,
			lauser=users["main"],
			lauser_name=p + "main",
			alworker=p + "main",
			alfrom_date="2026-04-01",
			alto_date="2026-04-01",
			status=status,
			workflow_state=status,
		)
	other_leave = source(
		"Application For Leave",
		"AFL-other",
		lauser=users["other"],
		status="На согласовании",
		workflow_state="На согласовании",
	)
	expenses = {}
	for state, approval in (
		("Черновик", "Draft"),
		("На согласовании", "Draft"),
		("Согласовано", "Approved"),
		("Отклонено", "Rejected"),
	):
		expenses[state] = source(
			"Expense Claim",
			"EC-" + state,
			employee=p + "main",
			employee_name=p + "main",
			company=company,
			approval_status=approval,
			workflow_state=state,
			expense_approver=users["other"],
			posting_date="2026-05-01",
			docstatus=int(approval == "Approved"),
		)
		frappe.db.set_value("Expense Claim", expenses[state], "owner", "Administrator", update_modified=False)
	other_expense = source(
		"Expense Claim",
		"EC-other",
		employee=p + "other",
		employee_name=p + "other",
		company=company,
		approval_status="Draft",
		workflow_state="На согласовании",
		expense_approver=users["other"],
		posting_date="2026-05-01",
	)
	source(
		"Expense Claim",
		"EC-orphan",
		employee=None,
		company=company,
		approval_status="Draft",
		workflow_state="На согласовании",
		posting_date="2026-05-01",
	)
	positions = []
	for i in range(25):
		status = {22: "Approved", 23: "Editing"}.get(i, "Pending Approval")
		who = "other" if i < 22 else "main"
		issue = source(
			"Issue", f"Issue-{i}", subject=p + f"Document {i}", status="Open", project=p + "Project"
		)
		positions.append(
			source(
				"User Timesheet Position",
				f"UTP-{i:02}",
				user_timesheet=other_timesheet if who == "other" else ut["Draft"],
				user=users[who],
				status=status,
				workflow_state=status,
				custom_username=p + who,
				period="2026-01-01",
				project=p + "Project",
				project_role=p + "Role",
				document_type="Issue",
				document_name=issue,
				all_hours=i + 1,
			)
		)

	mandatory = p + "Mandatory"
	optional = p + "Optional"
	workflows = {}
	for doctype in SOURCES:
		workflow = p + doctype
		insert("Workflow", workflow, workflow_name=workflow, document_type=doctype, is_active=0)
		workflows[doctype] = workflow
		for state, is_optional in ((mandatory, 0), (optional, 1)):
			insert(
				"Workflow Document State",
				frappe.generate_hash(length=20),
				parent=workflow,
				parenttype="Workflow",
				parentfield="states",
				state=state,
				is_optional_state=is_optional,
			)

	def task(dt, name, completed=False, user=None, round_status=None, state=None, targets=None):
		wf = workflows[dt]
		pending = "Pending Approval" if dt == "User Timesheet Position" else "На согласовании"
		approved = "Approved" if dt == "User Timesheet Position" else "Согласовано"
		t = _manual_task(
			doctype=dt,
			name=name,
			workflow=wf,
			state=state or pending,
			approver=user or users["main"],
			round_status=round_status or ("Transitioned" if completed else "Open"),
			status="Completed" if completed else "Working",
			round_id=frappe.generate_hash(length=40),
		)
		frappe.db.set_value(
			"Workflow Task",
			t,
			{
				"source_title": name,
				"source_owner": frappe.db.get_value(dt, name, "owner"),
				"next_state": approved if completed else None,
			},
		)
		if not completed:
			for target in targets or (mandatory,):
				insert(
					"Available Workflow Transitions",
					frappe.generate_hash(length=20),
					parent=t,
					parenttype="Workflow Task",
					parentfield="available_workflow_transitions",
					next_state=target,
				)
		return t

	for name in positions[:21]:
		task("User Timesheet Position", name)
	task("User Timesheet Position", positions[21], targets=(optional,))
	task("User Timesheet Position", positions[24], targets=(optional, mandatory))
	task("User Timesheet Position", positions[22], True)
	task("User Timesheet Position", positions[22], True)
	task("User Timesheet Position", positions[23], True)
	task("Application For Leave", leaves["На согласовании"], targets=(optional,))
	task("Application For Leave", other_leave)
	task("Application For Leave", leaves["Согласовано"], True)
	task("Application For Leave", leaves["Редактирование"], True)
	task("Expense Claim", expenses["На согласовании"], targets=(optional,))
	task("Expense Claim", other_expense)
	task("Expense Claim", other_expense, user=users["other"])
	task("Expense Claim", expenses["Согласовано"], True)
	# A pre-existing population permits deterministic daily-percentage checks.
	for dt, name in created:
		frappe.db.set_value(dt, name, "creation", add_days(now_datetime(), -3), update_modified=False)
	expected = {
		"Моих Таймшитов всего": [*ut.values(), *legacy],
		"Моих таймшитов на редактировании": [ut["Draft"], ut["Rework"], *legacy],
		"Моих таймшитов на согласовании": [ut["Pending Approval"]],
		"Мои отклоненные таймшиты": [ut["Rejected"]],
		"Мои просроченные таймшиты": [ut["Draft"], ut["Rejected"]],
		"Мои согласованные таймшиты": [ut["Approved"]],
		"Моих Заявок всего": list(leaves.values()),
		"Моих Заявок на согласовании": [leaves["На согласовании"]],
		"Моих Заявок Согласовано": [leaves["Согласовано"]],
		"Моих Заявок Отклонено": [leaves["Отклонено"]],
		"Всего заявок на расходы": list(expenses.values()),
		"Заявок EC на согласовании": [expenses["На согласовании"]],
		"Заявок EC Согласовано": [expenses["Согласовано"]],
		"Заявок EC Отклонено": [expenses["Отклонено"]],
		"ТШ у меня на согласовании-2": [*positions[:21], positions[24]],
		"ТШ согласованные мной-1": [positions[22]],
		"Заявки на отсутствие у меня на согласовании-2": [other_leave],
		"Заявки на отсутствие согласованные мной-1": [leaves["Согласовано"]],
		"Заявок EC у меня на согласовании": [other_expense],
		"Заявок EC Согласованных мной": [expenses["Согласовано"]],
	}
	workspace = frappe.get_doc("Workspace", "My Timesheets")
	result = {
		"version": VERSION,
		"workspace_content": frappe.parse_json(workspace.content),
		"workspace_cards": [{"name": c.number_card_name, "label": c.label} for c in workspace.number_cards],
		"namespace": namespace,
		"user": users["main"],
		"other": users["other"],
		"empty": users["empty"],
		"password": PASSWORD,
		"employee": p + "main",
		"expected": expected,
		"reopened_position": positions[23],
		"created": created,
	}
	path.write_text(json.dumps(result, ensure_ascii=False, default=str))
	frappe.clear_cache()
	return result


def effective_filters(card, user, employee):
	filters = frappe.parse_json(card.filters_json or "[]")
	if card.type == "Custom":
		return filters
	for dt, field, op, _expression, *_ in frappe.parse_json(card.dynamic_filters_json or "[]"):
		value = (
			[employee]
			if field == "employee"
			else (("set" if employee else "not set") if field == "name" and op == "is" else user)
		)
		filters.append([dt, field, op, value])
	return filters


def evaluate(fixture):
	from frappe.desk.doctype.number_card.number_card import get_result

	result = []
	for name, expected in fixture["expected"].items():
		card = frappe.get_doc("Number Card", name)
		filters = effective_filters(card, frappe.session.user, fixture["employee"])
		if card.type == "Custom":
			try:
				payload = frappe.get_attr(card.method)(filters=filters)
			except Exception as exc:
				raise AssertionError((name, card.type, filters)) from exc
			value = payload["value"]
			dt = card.document_type if card.document_type != "Workflow Task" else filters["doc"]
			query = []
			for field, route_value in payload["route_options"].items():
				if (
					isinstance(route_value, list)
					and route_value
					and isinstance(route_value[0], str)
					and route_value[0].startswith("[")
				):
					query.extend([[dt, field, *json.loads(v)] for v in route_value])
				else:
					query.append(
						[dt, field, *(route_value if isinstance(route_value, list) else ["=", route_value])]
					)
		else:
			value = get_result(card, filters)
			dt, query = card.document_type, filters
		rows = frappe.get_list(dt, filters=query, pluck="name", limit_page_length=0)
		result.append({"card": name, "value": value, "names": rows, "expected": expected})
	return result


@whitelist_for_tests
def seed_cards(namespace="cypress"):
	return seed(namespace)


@whitelist_for_tests
def cleanup_cards(namespace="cypress"):
	return cleanup(namespace)


def cli_seed(namespace="cypress"):
	"""Trusted bench entrypoint; no administrator browser password is needed."""
	previous = frappe.flags.in_test
	try:
		frappe.flags.in_test = True
		if namespace == "cypress":
			cleanup(namespace)
		return seed(namespace)
	finally:
		frappe.flags.in_test = previous


def cli_cleanup(namespace="cypress"):
	previous = frappe.flags.in_test
	try:
		frappe.flags.in_test = True
		return cleanup(namespace)
	finally:
		frappe.flags.in_test = previous


def cli_report(namespace="demo"):
	data = cli_seed(namespace)
	previous = frappe.session.user
	try:
		frappe.set_user(data["user"])
		rows = evaluate(data)
		for row in rows:
			row["passed"] = row["value"] == len(row["expected"]) and sorted(row["names"]) == sorted(
				row["expected"]
			)
		return {"user": data["user"], "cards": rows, "passed": all(row["passed"] for row in rows)}
	finally:
		frappe.set_user(previous)


def cli_repair_permissions():
	previous = frappe.flags.in_test
	try:
		frappe.flags.in_test = True
		guard()
		for namespace in ("test", "cypress", "demo"):
			role = identity(namespace) + "Reader"
			frappe.db.delete("Custom DocPerm", {"role": role})
			if frappe.db.exists("Role", role):
				grant_read_permissions(role)
		frappe.clear_cache()
		return {
			dt: sorted({p.role for p in frappe.get_meta(dt).permissions})
			for dt in ("Number Card", "Workspace", "Timesheet Settings")
		}
	finally:
		frappe.flags.in_test = previous


def cli_reopen():
	previous = frappe.flags.in_test
	try:
		frappe.flags.in_test = True
		guard()
		path = state_path("cypress")
		data = json.loads(path.read_text())
		name = identity("cypress") + "AFL-Согласовано"
		frappe.db.set_value(
			"Application For Leave", name, {"status": "Редактирование", "workflow_state": "Редактирование"}
		)
		data["expected"]["Моих Заявок Согласовано"] = []
		data["expected"]["Заявки на отсутствие согласованные мной-1"] = []
		path.write_text(json.dumps(data, ensure_ascii=False, default=str))
		return {"expected": data["expected"], "source": name}
	finally:
		frappe.flags.in_test = previous
