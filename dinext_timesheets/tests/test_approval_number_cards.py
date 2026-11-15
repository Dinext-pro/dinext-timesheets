import json
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

import frappe


class TestApprovalNumberCards(TestCase):
	def test_timesheet_and_leave_cards_use_the_owning_app_method(self):
		card_path = Path(__file__).resolve().parents[1] / "dinext_timesheets" / "number_card"
		cards = []
		for path in card_path.glob("*/*.json"):
			card = json.loads(path.read_text())
			filters = json.loads(card.get("filters_json") or "null")
			if isinstance(filters, dict) and filters.get("doc") in ("User Timesheet Position", "Application For Leave"):
				cards.append(card)
		self.assertEqual(len(cards), 4)
		for card in cards:
			with self.subTest(card=card["name"]):
				self.assertEqual(
					card["method"], "dinext_timesheets.workflow_approval.get_approval_number_card_result"
				)

	def test_source_status_is_selected_by_the_timesheets_endpoint(self):
		from dinext_timesheets.workflow_approval import get_approval_number_card_result

		with patch("dinext_common.workflow_approval.api.calculate_approval_number_card", create=True) as calculate:
			for doctype, route in (
				("User Timesheet Position", "user-timesheet-position"),
				("Application For Leave", "application-for-leave"),
			):
				filters = {"doc": doctype, "state": "Approved", "route": route}
				self.assertIs(get_approval_number_card_result(json.dumps(filters)), calculate.return_value)
				calculate.assert_called_with(filters, source_state_field="status")

			with self.assertRaises(frappe.ValidationError):
				get_approval_number_card_result({"doc": "Expense Claim", "state": "Approved", "route": "expense-claim"})
			self.assertEqual(calculate.call_count, 2)

	def test_cards_support_the_previous_common_release(self):
		from dinext_common.workflow_approval import api
		from dinext_timesheets.workflow_approval import get_approval_number_card_result

		filters = {"doc": "Application For Leave", "state": "Approved", "route": "application-for-leave"}
		with (
			patch.object(api, "calculate_approval_number_card", None, create=True),
			patch.object(api, "get_legacy_number_card_result") as legacy,
		):
			self.assertIs(get_approval_number_card_result(filters), legacy.return_value)
			legacy.assert_called_once_with(filters)
