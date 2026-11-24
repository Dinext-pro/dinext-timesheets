import json
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

import frappe


class TestDeadlineWorkspaceCharts(TestCase):
	@staticmethod
	def shipped_workspace():
		root = Path(__file__).resolve().parents[1]
		return json.loads(
			(root / "dinext_timesheets/workspace/my_timesheets/my_timesheets.json").read_text()
		)

	def test_shipped_workspace_places_both_overdue_cards(self):
		workspace = self.shipped_workspace()
		blocks = json.loads(workspace["content"])
		cards = [block["data"].get("number_card_name") for block in blocks]
		personal = cards.index("Overdue Timesheets")
		deadline = next(index for index, block in enumerate(blocks) if block["id"] == "deadline-control")
		self.assertEqual(cards[personal - 1:personal + 2], [
			"Rejected Timesheets", "Overdue Timesheets", "Approved Timesheets",
		])
		self.assertEqual(cards[deadline + 1], "Timesheets Overdue for Submission")
		self.assertEqual(cards.count("Overdue Timesheets"), 1)
		self.assertEqual(cards.count("Timesheets Overdue for Submission"), 1)
		links = {row["label"]: row["number_card_name"] for row in workspace["number_cards"]}
		self.assertEqual(links["Overdue Timesheets"], "Мои просроченные таймшиты")
		self.assertEqual(links["Timesheets Overdue for Submission"], "Timesheets Overdue for Submission")

	def test_upgrade_moves_old_card_and_preserves_other_blocks(self):
		from dinext_timesheets.patches.v1_0.restore_overdue_timesheet_cards import place_overdue_cards

		blocks = json.loads(self.shipped_workspace()["content"])
		overdue = next(b for b in blocks if b["data"].get("number_card_name") == "Overdue Timesheets")
		overall = next(b for b in blocks if b["data"].get("number_card_name") == "Timesheets Overdue for Submission")
		note = {"id": "custom-note", "type": "paragraph", "data": {"text": "Workspace note"}}
		previous = [
			{**overdue, "data": {"col": 4, "number_card_name": "тш просрочено"}} if block == overall else block
			for block in blocks if block != overdue
		]
		previous.insert(1, note)
		blocks.insert(1, note)
		updated = place_overdue_cards(previous)
		self.assertEqual(updated, blocks)
		self.assertEqual(place_overdue_cards(updated), updated)

	def test_upgrade_creates_missing_chart_dependencies_before_workspace_save(self):
		from types import SimpleNamespace

		from dinext_timesheets.patches.v1_0.refine_deadline_workspace import CHARTS, execute

		created = set()
		workspace = SimpleNamespace(content='[]', charts=[])
		workspace.append = lambda field, row: workspace.charts.append(SimpleNamespace(**row))
		workspace.save = lambda **kwargs: self.assertEqual(created, set(CHARTS))
		def exists(doctype, name):
			return doctype == "Workspace" or name in created
		def reload(module, doctype, name, **kwargs):
			created.update(chart for chart in CHARTS if frappe.scrub(chart) == name)
		with (
			patch.object(frappe.db, "exists", side_effect=exists),
			patch.object(frappe, "reload_doc", side_effect=reload),
			patch.object(frappe, "get_doc", side_effect=lambda doctype, name: workspace if doctype == "Workspace" else SimpleNamespace(chart_type="Custom")),
		):
			execute()
		self.assertEqual({row.chart_name for row in workspace.charts}, set(CHARTS))

	def test_current_counts_are_unique_parents_per_responsible(self):
		from dinext_timesheets.submission_discipline import overdue_chart

		result = dict(
			rows=[
				dict(timesheet="TS-1", author="ivan", submission_overdue=True),
				dict(timesheet="TS-2", author="ivan", submission_overdue=True),
				dict(timesheet="TS-3", author="anna", submission_overdue=False),
			],
			approval_rows=[
				dict(timesheet="TS-1", approver="maria", discipline_status="Overdue"),
				dict(timesheet="TS-1", approver="maria", discipline_status="Overdue"),
				dict(timesheet="TS-1", approver="alexey", discipline_status="Overdue"),
				dict(timesheet="TS-2", approver="maria", discipline_status="On Time"),
			],
		)
		with patch(
			"dinext_common.workflow_approval.email_presentation.full_name",
			side_effect=lambda user: {
				"ivan": "Иван Петров",
				"maria": "Мария Соколова",
				"alexey": "Алексей Смирнов",
			}[user],
		):
			chart = overdue_chart(result, "Submission")
			self.assertEqual(chart["data"]["labels"], ["Иван Петров"])
			self.assertEqual(chart["data"]["datasets"][0]["values"], [2])
			chart = overdue_chart(result, "Approval")
			self.assertEqual(
				dict(zip(chart["data"]["labels"], chart["data"]["datasets"][0]["values"], strict=True)),
				{"Мария Соколова": 1, "Алексей Смирнов": 1},
			)

	def test_empty_chart_and_percentage_use_standard_widget_contracts(self):
		from dinext_timesheets.submission_discipline import _card, overdue_chart

		self.assertEqual(overdue_chart(dict(rows=[], approval_rows=[]))["data"]["labels"], [])
		with patch(
			"dinext_timesheets.submission_discipline.summary",
			return_value={"submission_percent": None, "overdue_timesheets": 0},
		):
			self.assertEqual(_card("submission_percent", percent=True)["value"], frappe._("No observations"))
			self.assertEqual(_card("submission_percent", percent=True)["fieldtype"], "Data")
			self.assertEqual(_card("overdue_timesheets")["value"], 0)

	def test_layout_upgrade_is_idempotent_and_preserves_unrelated_blocks(self):
		from dinext_timesheets.patches.v1_0.refine_deadline_workspace import arrange

		blocks = [
			dict(id="custom", type="paragraph", data={"text": "Business note"}),
			dict(id="approvals", type="header", data={"text": "My Approvals"}),
			dict(id="reports", type="header", data={"text": "Timesheet Reports"}),
			dict(id="config", type="header", data={"text": "Timesheet Configuration"}),
			dict(
				id="deadline-card-0",
				type="number_card",
				data={"number_card_name": "On-time Timesheet Submissions"},
			),
			dict(
				id="deadline-report", type="shortcut", data={"shortcut_name": "Timesheet Deadline Discipline"}
			),
		]
		updated = arrange(blocks)
		self.assertEqual(arrange(updated), updated)
		self.assertEqual(updated[0], blocks[0])
		self.assertLess(
			next(i for i, b in enumerate(updated) if b["id"] == "deadline-card-0"),
			next(i for i, b in enumerate(updated) if b["id"] == "reports"),
		)
		self.assertEqual(updated[-1]["id"], "config")

	def test_previous_standard_layout_is_replaced_and_custom_workspace_is_preserved(self):
		from dinext_timesheets.patches.v1_0 import restore_standard_my_timesheets_layout as migration

		shipped = self.shipped_workspace()
		blocks = json.loads(shipped["content"])
		removed_cards = {
			"Total Expense Claims", "On-time Timesheet Submissions", "On-time Timesheet Approvals",
			"Overdue Timesheet Approvals", "Overdue Timesheet Positions", "Timesheet Hours Awaiting Approval",
		}
		removed_shortcuts = {"Timesheet Settings", "Timesheet Deadline Discipline"}
		legacy_blocks = [
			block for block in blocks
			if block["data"].get("number_card_name") not in removed_cards
			and block["data"].get("shortcut_name") not in removed_shortcuts
		]
		workspace = frappe._dict(
			content=json.dumps(legacy_blocks), public=1, module="Dinext Timesheets",
			number_cards=[row for row in shipped["number_cards"] if row["label"] not in removed_cards],
			charts=shipped["charts"],
			shortcuts=[row for row in shipped["shortcuts"] if row["label"] not in removed_shortcuts],
			for_user=None, links=[], custom_blocks=[], quick_lists=[],
		)
		self.assertTrue(migration._is_earlier_standard(workspace, shipped, legacy_blocks, blocks))
		extra = dict(type="paragraph", data={"text": "Site-specific instructions"})
		self.assertFalse(migration._is_earlier_standard(workspace, shipped, [*legacy_blocks, extra], blocks))
		workspace.number_cards = shipped["number_cards"]
		workspace.shortcuts = shipped["shortcuts"]
		self.assertFalse(migration._is_earlier_standard(workspace, shipped, blocks, blocks))

	def test_obsolete_management_column_is_removed_only_after_metadata(self):
		from unittest.mock import Mock, call

		from dinext_timesheets.patches.v1_0 import drop_obsolete_timesheet_management_column as migration

		db = Mock()
		db.has_column.side_effect = [True, False]
		meta = Mock()
		meta.has_field.return_value = False
		qb = Mock()
		qb.DocType.return_value.get_sql.return_value = "`tabWorkflow Transition`"
		cache = Mock()
		runtime = Mock(db=db, cache=cache, conf=frappe._dict(), qb=qb, get_meta=Mock(return_value=meta))
		with patch.object(migration, "frappe", runtime):
			migration.execute()
			migration.execute()

		db.sql_ddl.assert_called_once_with(
			"ALTER TABLE `tabWorkflow Transition` DROP COLUMN custom_timesheet_management_action"
		)
		meta.has_field.assert_called_once_with("custom_timesheet_management_action")
		self.assertEqual(cache.hdel.call_args_list, [call("table_columns", "tabWorkflow Transition")] * 3)
