import json
import unittest
from pathlib import Path


class TestUTPEditFixture(unittest.TestCase):
	def test_position_fixture_uses_the_native_status_link(self):
		app = Path(__file__).resolve().parents[1]
		workflows = json.loads((app / "fixtures/workflow.json").read_text())
		position_workflows = [
			workflow for workflow in workflows if workflow["document_type"] == "User Timesheet Position"
		]
		self.assertTrue(position_workflows)
		self.assertEqual({workflow["workflow_state_field"] for workflow in position_workflows}, {"status"})
		self.assertEqual(
			next(workflow for workflow in workflows if workflow["name"] == "AFL Workflow")["workflow_state_field"],
			"workflow_state",
		)
		path = app / "dinext_timesheets/doctype/user_timesheet_position/user_timesheet_position.json"
		fields = {field["fieldname"]: field for field in json.loads(path.read_text())["fields"]}
		self.assertEqual((fields["status"]["fieldtype"], fields["status"]["options"]), ("Link", "Workflow State"))

	def test_return_transitions_share_the_edit_action(self):
		path = Path(__file__).resolve().parents[1] / "fixtures/workflow.json"
		workflows = {workflow["name"]: workflow for workflow in json.loads(path.read_text())}
		self.assertEqual(
			{
				(row["state"], row["action"])
				for row in workflows["UTP Workflow"]["transitions"]
				if row["next_state"] == "Editing"
			},
			{("Pending Approval", "Edit"), ("Rejected", "Edit"), ("Approved", "Edit")},
		)
		self.assertIn("Stop Workflow", {row["action"] for row in workflows["AFL Workflow"]["transitions"]})
