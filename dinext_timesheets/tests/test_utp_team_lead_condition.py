from unittest import TestCase
from unittest.mock import Mock, patch

import frappe

from dinext_timesheets.patches.v1_0 import configure_parallel_workflows, configure_parallel_workflows_v2
from dinext_timesheets.patches.v1_0.utp_team_lead_condition import NEW_ROLE, OLD_ROLE, migrate_condition
from dinext_timesheets.workflow_localization import label_rules, leave_label_rules


LOOKUP = 'frappe.db.get_value("Has Role", {"parent": frappe.session.user, "role": "Z_Dinord_Team_Lead"}, "role")'
CONDITION = f'({LOOKUP} and frappe.db.get_value("Teamleads Table", {{"parent": doc.user_group, "teamlead": frappe.session.user}}, "name")) or doc.user == frappe.session.user'


class TestLegacyUTPTeamLeadCondition(TestCase):
	def test_both_migrations_preserve_or_rename_the_installed_condition(self):
		for patch_module in (configure_parallel_workflows, configure_parallel_workflows_v2):
			for new_members in (("existing",), ("existing", "additional"), (), ("additional",)):
				with self.subTest(patch=patch_module.__name__, new_members=new_members):
					members = [frappe._dict(role=OLD_ROLE, parent="existing")]
					members.extend(frappe._dict(role=NEW_ROLE, parent=member) for member in new_members)
					row = frappe._dict(name="test-transition", condition=CONDITION, action="Edit", next_state="Editing")

					def rows(doctype, **kwargs):
						if doctype == "Workflow Transition" and kwargs["filters"].get("parent") == "UTP Workflow":
							return [row]
						if doctype == "Has Role":
							self.assertEqual(kwargs["filters"], {"role": ("in", [OLD_ROLE, NEW_ROLE])})
							return members
						return []

					with (
						patch.object(frappe, "get_all", side_effect=rows),
						patch.object(frappe, "db", Mock()) as db,
						patch.object(frappe, "clear_cache"),
						patch.object(configure_parallel_workflows_v2, "_ensure_workflow_task_permissions"),
					):
						db.exists.return_value = False
						patch_module.execute()
						updates = [call.args for call in db.set_value.call_args_list if call.args[0] == "Workflow Transition"]
					if new_members == ("existing",):
						self.assertEqual(len(updates), 1)
						value = updates[0][2]
						condition = value["condition"] if isinstance(value, dict) else updates[0][3]
						self.assertEqual(condition, CONDITION.replace(OLD_ROLE, NEW_ROLE))
					else:
						self.assertEqual(updates, [])

	def test_custom_string_comparisons_and_unrelated_literals_are_untouched(self):
		for condition in (f'{LOOKUP} == "other"', 'doc.name == "Z_Dinord_Team_Lead"', "invalid Z_Dinord_Team_Lead ("):
			with self.subTest(condition=condition), patch.object(frappe, "get_all") as query:
				self.assertEqual(migrate_condition(condition), condition)
				query.assert_not_called()

	def test_signed_alias_is_scoped_to_utp(self):
		self.assertEqual(label_rules()["legacy_signed_action_aliases"], (("Pending Approval", "Stop Workflow", "Edit", "Editing"),))
		self.assertNotIn("legacy_signed_action_aliases", leave_label_rules())
