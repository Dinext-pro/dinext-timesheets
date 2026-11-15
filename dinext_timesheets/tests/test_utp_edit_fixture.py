import json
import unittest
from pathlib import Path


class TestUTPEditFixture(unittest.TestCase):
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
