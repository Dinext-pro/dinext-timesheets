"""Keep installed domain templates and profiles available to the shared mailer."""

import importlib
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import frappe

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

        workflow = SimpleNamespace(
            name="UTP Workflow",
            states=[
                SimpleNamespace(state="Editing"),
                SimpleNamespace(state="Pending Approval"),
                SimpleNamespace(state="Rejected"),
            ],
            transitions=[],
        )
        configure_workflow(workflow, now="2026-01-01 00:00:00")
        self.assertEqual(workflow.custom_group_email_template, DIGEST)
        self.assertEqual([state.send_email for state in workflow.states], [0, 1, 1])
        self.assertEqual(workflow.states[2].next_action_email_template, "Dinext Timesheet Workflow Correction")
