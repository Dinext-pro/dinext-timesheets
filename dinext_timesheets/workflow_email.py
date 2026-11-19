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


def previous_approval_email_templates():
	"""Recognize the shared defaults shipped before the layout moved here."""
	previous_shared_template = {
		"subject": '{{ header_title }}: {{ timesheet_title if is_timesheet else document_title|truncate(100) }}',
		"response_html": '{% include "templates/emails/dinext_workflow.html" %}',
	}
	return {name: (previous_shared_template,) for name in ("Dinext Workflow Action", "Dinext Workflow Correction")}


def approval_email_profiles():
	return {
		"Application For Leave": {
			"workflow": "AFL Workflow",
			"approval_states": ("Pending Approval",),
		},
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


def email_dependencies(source):
	if source.doctype == "User Timesheet Position":
		linked = [
			(doctype, name)
			for doctype, name in (
				("User Timesheet", source.user_timesheet),
				("Project", source.project),
				(source.document_type, source.document_name),
				("Project Role", source.project_role),
			)
			if doctype and name
		]
		for position in _positions(source):
			if position.name == source.name:
				break
			linked.append((source.doctype, position.name))
		return linked
	return []


def position_ordinals(rows):
	return {row["name"]: number for number, row in enumerate(rows, start=1)}


def position_label(number, project, task, role):
	description = f"{project or '—'} — {task or '—'} — {role or '—'}"
	return f"№ {number} — {description}" if number else description


def _title(doctype, name, recipient=None):
	if not name or not doctype:
		return ""
	meta = frappe.get_meta(doctype)
	title_field = meta.title_field
	if not title_field or title_field == "name":
		return name
	if not recipient:
		return frappe.db.get_value(doctype, name, title_field) or name
	from dinext_common.workflow_approval.email_access import visible_document
	from dinext_common.workflow_approval.engine import _has_source_read_permission

	try:
		doc = frappe.get_doc(doctype, name)
	except frappe.DoesNotExistError:
		return name
	if not _has_source_read_permission(doc, recipient):
		return name
	return visible_document(doc, recipient).get(title_field) or name


def _positions(source):
	return frappe.get_all(
		"User Timesheet Position", filters={"user_timesheet": source.get("user_timesheet")},
		fields=["name"],
		order_by="creation asc, name asc",
	)


def _position(source, recipient=None):
	if not source.get("user_timesheet"):
		return None
	parent = frappe.get_doc("User Timesheet", source.user_timesheet)
	ordered = _positions(source)
	ordinal = position_ordinals(ordered).get(source.name)
	if recipient:
		from dinext_common.workflow_approval.email_access import recipient_user, visible_document
		from dinext_timesheets.workflow_form_references import timesheet_positions

		if recipient != "Administrator" and ordinal and ordinal > 1:
			with recipient_user(recipient):
				_, allowed = timesheet_positions(parent)
			if not {row.name for row in ordered[:ordinal - 1]}.issubset(allowed):
				ordinal = None
		parent = visible_document(parent, recipient)
	label = position_label(
		ordinal,
		_title("Project", source.get("project"), recipient),
		_title(source.get("document_type"), source.get("document_name"), recipient),
		_title("Project Role", source.get("project_role"), recipient),
	)
	return dict(
		timesheet_name=parent.name,
		author=parent.get("timesheet_from"),
		period_from=parent.get("ts_valid_from"),
		period_to=parent.get("ts_valid_for"),
		position_name=source.name,
		ordinal=ordinal,
		position_label=label,
		hours=float(source.get("all_hours") or 0),
		hours_details=[
			dict(hours=float(row.get("hours") or 0), description=row.get("description") or "")
			for row in source.get("table") or []
			if float(row.get("hours") or 0) != 0
		],
		link=get_url_to_form("User Timesheet", parent.name),
	)


def digest_item(task, *, source=None, recipient=None):
	if task.reference_doctype == "Application For Leave":
		source = source if source is not None else frappe.get_doc(task.reference_doctype, task.reference_name)
		return dict(group_key=task.reference_doctype + ":" + source.name, title=leave_title(source))
	if task.reference_doctype != "User Timesheet Position":
		return None
	source = source if source is not None else frappe.get_doc("User Timesheet Position", task.reference_name)
	row = _position(source, recipient)
	if row is None:
		return {"group_key": f"User Timesheet Position:{source.name}"}
	return {**row, "group_key": "User Timesheet Position:" + source.name, "title": row["position_label"]}


def email_context(task, source):
	if source.doctype == "Application For Leave":
		return dict(document_title=leave_title(source))
	if source.doctype != "User Timesheet Position":
		return None
	row = _position(source, frappe.session.user)
	if row is None:
		return None
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

	user = source.get("lauser")
	return source.name.replace(user, full_name(user)) if user else source.name
