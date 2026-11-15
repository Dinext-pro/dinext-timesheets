"""Timesheet email defaults and rows in the canonical card order."""

import json
from functools import lru_cache
from pathlib import Path

import frappe
from frappe.utils import get_url_to_form


DIGEST = "Dinext Timesheet Workflow Digest"
DEADLINE = "Dinext Timesheet Workflow Deadline Digest"


@lru_cache(maxsize=1)
def _template_fixture():
	fixture = Path(__file__).with_name("fixtures") / "email_template.json"
	return json.loads(fixture.read_text(encoding="utf-8"))


def ensure_approval_email_templates():
	"""Supply missing links needed by old patches before fixtures are synchronized."""
	for row in _template_fixture():
		if not frappe.db.exists("Email Template", row["name"]):
			frappe.get_doc(row.copy()).insert(ignore_permissions=True)


@lru_cache(maxsize=1)
def approval_email_templates():
	"""Load standard bodies from the same fixture installed into Email Template."""
	templates = {
		row["name"]: {"current": {field: row[field] for field in ("subject", "response_html")}}
		for row in _template_fixture()
		if row["name"] in (DIGEST, DEADLINE)
	}
	templates[DIGEST]["previous"] = (
		{
			"subject": '{{ _("Timesheets awaiting approval") }}',
			"response_html": (
				'<p>{{ _("Timesheets awaiting approval") }}</p><ul>'
				'{% for row in rows %}<li><a href="{{ row.link|e }}">{{ row.title|e }}</a>'
				' — {{ row.count }} {{ _("position(s)") }}</li>{% endfor %}</ul>'
			),
		},
		{
			"subject": "Timesheets awaiting approval",
			"response_html": (
				"<p>Timesheets awaiting approval:</p><ul>"
				'{% for row in rows %}<li><a href="{{ row.link }}">'
				"{{ row.title }}</a> — {{ row.count }} position(s)</li>{% endfor %}</ul>"
			),
		},
	)
	return templates


def approval_email_profiles():
	return {
		"User Timesheet Position": {
			"workflow": "UTP Workflow",
			"approval_states": ("Pending Approval",),
			"digest_template": DIGEST,
			"deadline_template": DEADLINE,
			"correction_template": "Dinext Timesheet Workflow Correction",
		},
	}


def can_receive(task, source, recipient):
	if source.doctype != "User Timesheet Position":
		return None
	from dinext_common.workflow_approval.engine import _has_source_read_permission

	if not source.user_timesheet or not frappe.db.exists("User Timesheet", source.user_timesheet):
		return False
	return _has_source_read_permission(frappe.get_doc("User Timesheet", source.user_timesheet), recipient)


def position_ordinals(rows):
	return {row["name"]: number for number, row in enumerate(rows, start=1)}


def position_label(number, project, task, role):
	return f"№ {number} — {project or '—'} — {task or '—'} — {role or '—'}"


def _title(doctype, name):
	if not name or not doctype:
		return ""
	meta = frappe.get_meta(doctype)
	title_field = meta.title_field
	return (frappe.db.get_value(doctype, name, title_field) if title_field else name) or name


def _position(source):
	parent = frappe.get_doc("User Timesheet", source.user_timesheet)
	ordered = frappe.get_all(
		"User Timesheet Position",
		filters={"user_timesheet": parent.name},
		fields=["name"],
		order_by="creation asc, name asc",
	)
	ordinal = position_ordinals(ordered).get(source.name)
	label = position_label(
		ordinal,
		_title("Project", source.project),
		_title(source.document_type, source.document_name),
		_title("Project Role", source.project_role),
	)
	return dict(
		timesheet_name=parent.name,
		author=parent.timesheet_from,
		period_from=parent.ts_valid_from,
		period_to=parent.ts_valid_for,
		position_name=source.name,
		ordinal=ordinal,
		position_label=label,
		hours=float(source.all_hours or 0),
		hours_details=[
			dict(hours=float(row.hours or 0), description=row.description or "")
			for row in source.get("table") or []
			if float(row.hours or 0) != 0
		],
		link=get_url_to_form("User Timesheet", parent.name),
	)


def digest_item(task):
	if task.reference_doctype == "Application For Leave":
		source = frappe.get_doc(task.reference_doctype, task.reference_name)
		return dict(group_key=task.reference_doctype + ":" + source.name, title=leave_title(source))
	if task.reference_doctype != "User Timesheet Position":
		return None
	source = frappe.get_doc("User Timesheet Position", task.reference_name)
	row = _position(source)
	return {**row, "group_key": "User Timesheet Position:" + source.name, "title": row["position_label"]}


def email_context(task, source):
	if source.doctype == "Application For Leave":
		return dict(document_title=leave_title(source))
	if source.doctype != "User Timesheet Position":
		return None
	row = _position(source)
	return dict(
		timesheet_title=row["timesheet_name"],
		timesheet_link=row["link"],
		timesheet_period_from=row["period_from"],
		timesheet_period_to=row["period_to"],
		position_label=row["position_label"],
		hours=row["hours"],
		hours_details=row["hours_details"],
		document_title=row["position_label"],
		document_link=row["link"],
	)


def leave_title(source):
	from dinext_common.workflow_approval.email_presentation import full_name

	return source.name.replace(source.lauser, full_name(source.lauser)) if source.lauser else source.name
