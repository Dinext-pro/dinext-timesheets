"""Keep installed domain templates and profiles available to the shared mailer."""

import importlib
import unittest
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe import translate
from jinja2 import Environment, FileSystemLoader

from dinext_timesheets import hooks


DIGEST = "Dinext Timesheet Workflow Digest"
DEADLINE = "Dinext Timesheet Workflow Deadline Digest"


def resolve(path):
    module, attr = path.rsplit(".", 1)
    return getattr(importlib.import_module(module), attr)


class TestWorkflowEmailOwnership(unittest.TestCase):
    def setUp(self):
        for context in (
            patch.object(frappe, "local", SimpleNamespace(site="test-site")),
            patch.object(frappe, "get_hooks", lambda name: getattr(hooks, name, [])),
            patch.object(frappe, "get_attr", resolve),
        ):
            context.start()
            self.addCleanup(context.stop)

    def test_shared_renderer_resolves_owned_digest_without_a_database_record(self):
        from dinext_common.workflow_approval.email_templates import default_email_templates, renderable_email_templates

        common = default_email_templates()
        self.assertNotIn(DIGEST, common)
        self.assertNotIn(DEADLINE, common)
        templates = renderable_email_templates()
        for name in (DIGEST, DEADLINE):
            self.assertEqual(
                templates[name],
                {
                    "subject": "{{ header_title }}: {{ summary }}",
                    "response_html": '{% include "templates/emails/dinext_workflow.html" %}',
                },
            )

    def test_historical_defaults_are_recognized_but_administrator_edits_are_kept(self):
        from dinext_common.workflow_approval.email_templates import is_known_default_template

        old = {
            "use_html": 1,
            "subject": "Timesheets awaiting approval",
            "response_html": (
                "<p>Timesheets awaiting approval:</p><ul>"
                '{% for row in rows %}<li><a href="{{ row.link }}">'
                "{{ row.title }}</a> — {{ row.count }} position(s)</li>{% endfor %}</ul>"
            ),
        }
        self.assertTrue(is_known_default_template(DIGEST, old))
        self.assertFalse(is_known_default_template(DIGEST, dict(old, subject="Site-specific approval digest")))

    def test_shared_historical_default_is_upgraded_while_edited_template_is_kept(self):
        from dinext_common.workflow_approval.email_templates import is_known_default_template

        name = "Dinext Workflow Action"
        old = {
            "use_html": 1,
            "subject": "{{ header_title }}: {{ timesheet_title if is_timesheet else document_title|truncate(100) }}",
            "response_html": '{% include "templates/emails/dinext_workflow.html" %}',
        }
        self.assertTrue(is_known_default_template(name, old))
        self.assertFalse(is_known_default_template(name, dict(old, response_html="<p>Site-specific body</p>")))

    def test_timesheet_digest_and_deadline_defaults_apply_to_custom_workflows(self):
        from dinext_common.workflow_approval.email_templates import domain_email_template

        tasks = (
            SimpleNamespace(reference_doctype="Project"),
            SimpleNamespace(reference_doctype="User Timesheet Position"),
        )
        self.assertEqual(domain_email_template(tasks, "digest_template"), DIGEST)
        self.assertEqual(domain_email_template(tasks, "deadline_template"), DEADLINE)
        self.assertIsNone(domain_email_template(tasks[:1], "digest_template"))

    def test_common_can_resolve_its_own_templates_without_timesheets_installed(self):
        from dinext_common.workflow_approval.email_migration import supported_workflow_names
        from dinext_common.workflow_approval.email_templates import renderable_email_templates

        with patch.object(frappe, "get_hooks", return_value=[]):
            templates = renderable_email_templates()
            self.assertIn("Dinext Workflow Digest", templates)
            self.assertNotIn(DIGEST, templates)
            self.assertNotIn("UTP Workflow", supported_workflow_names())

    def test_installed_timesheets_supply_the_initial_utp_mail_profile(self):
        from dinext_common.workflow_approval.email_migration import configure_workflow

        from dinext_timesheets.workflow_email import approval_email_profiles

        workflow = SimpleNamespace(
            name="UTP Workflow",
            states=[
                SimpleNamespace(state="Editing"),
                SimpleNamespace(state="Pending Approval"),
                SimpleNamespace(state="Rejected"),
            ],
            transitions=[],
        )
        configure_workflow(
            workflow,
            profile=approval_email_profiles()["User Timesheet Position"],
            now="2026-01-01 00:00:00",
        )
        self.assertEqual(workflow.custom_group_email_template, DIGEST)
        self.assertEqual([state.send_email for state in workflow.states], [0, 1, 1])
        self.assertEqual(workflow.states[2].next_action_email_template, "Dinext Timesheet Workflow Correction")

    def render_mixed_digest(self, *, with_timesheets=True):
        import dinext_common
        import dinext_timesheets
        from dinext_common.workflow_approval import email_presentation

        environment = Environment(
            loader=FileSystemLoader([Path(app.__file__).parent for app in (dinext_common, dinext_timesheets)])
        )
        environment.globals["_"] = lambda label: label
        context = {
            "rows": [
                {"doctype": "Project", "name": "PRJ-1", "title": "Ordinary project", "link": "/app/project/PRJ-1"},
                {
                    "doctype": "User Timesheet Position", "name": "UTP-1", "title": "Review hours",
                    "link": "/app/user-timesheet/UT-1", "timesheet_name": "UT-1", "position_label": "№ 1 — Review hours",
                    "period_from": "2026-11-09", "period_to": "2026-11-15", "hours": 2,
                    "hours_details": [{"hours": 2, "description": "<review>"}],
                },
            ],
        }
        with (
            patch.object(frappe, "get_hooks", lambda name: getattr(hooks, name, []) if with_timesheets else []),
            patch.object(frappe, "render_template", lambda string, args: environment.from_string(string).render(args)),
            patch.object(translate, "get_all_translations", return_value={}),
            patch.object(email_presentation, "language_context", return_value=nullcontext()),
            patch.object(email_presentation, "recipient_language", return_value="en"),
        ):
            return email_presentation.render_standard("Dinext Workflow Digest", context, None)

    def test_mixed_digest_displays_both_timesheet_groups_and_other_documents(self):
        subject, body = self.render_mixed_digest()
        self.assertIn("Timesheets: 1", subject)
        self.assertIn("Project: 1", subject)
        self.assertIn("/app/user-timesheet/UT-1", body)
        self.assertIn("2 h — &lt;review&gt;", body)
        self.assertIn("Ordinary project", body)

    def test_common_digest_without_providers_renders_all_documents_generically(self):
        subject, body = self.render_mixed_digest(with_timesheets=False)
        self.assertIn("User Timesheet Position: 1", subject)
        self.assertIn("Project: 1", subject)
        self.assertIn("Ordinary project", body)
        self.assertNotIn("Hours awaiting approval", body)
