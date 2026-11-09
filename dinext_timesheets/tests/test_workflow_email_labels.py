import unittest


class TestWorkflowEmailLabels(unittest.TestCase):
	def test_filtered_positions_keep_canonical_ordinals(self):
		from dinext_timesheets.workflow_email import position_ordinals

		rows = [dict(name="one"), dict(name="two"), dict(name="three"), dict(name="four"), dict(name="five")]
		numbers = position_ordinals(rows)
		self.assertEqual([numbers[name] for name in ["two", "five"]], [2, 5])

	def test_label_contains_human_components_and_original_number(self):
		from dinext_timesheets.workflow_email import position_label

		self.assertEqual(
			position_label(5, "Внедрение ERP", "Настроить согласование", "Разработчик"),
			"№ 5 — Внедрение ERP — Настроить согласование — Разработчик",
		)
