# ruff: noqa: RUF001 -- Russian card names and stored workflow states are intentional.
import frappe
from frappe.tests.utils import FrappeTestCase

from dinext_timesheets.tests import my_timesheets_cards_ui as fixture


class TestMyTimesheetsCards(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		cls.addClassCleanup(frappe.clear_cache)
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.fixture = fixture.seed("test")
		cls.addClassCleanup(lambda: fixture.state_path("test").unlink(missing_ok=True))

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.savepoint("number_card_case")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="number_card_case")
		super().tearDown()

	def test_all_20_card_counts_and_sources(self):
		frappe.set_user(self.fixture["user"])
		rows = fixture.evaluate(self.fixture)
		self.assertEqual(len(rows), 20)
		for row in rows:
			with self.subTest(card=row["card"]):
				self.assertEqual(row["value"], len(row["expected"]))
				self.assertCountEqual(row["names"], row["expected"])

	def test_empty_user_sees_no_sources(self):
		from dinext_projects_pl.expense_claim_cards import extend_bootinfo

		frappe.set_user(self.fixture["empty"])
		boot = frappe._dict()
		extend_bootinfo(boot)
		self.assertEqual(boot.dinext_expense_claim_employees, [])
		for row in fixture.evaluate({**self.fixture, "employee": ""}):
			self.assertEqual(row["value"], 0, row["card"])
			self.assertEqual(row["names"], [], row["card"])

	def test_boot_employee_mapping_uses_current_session(self):
		from dinext_projects_pl.expense_claim_cards import extend_bootinfo

		for who in ("user", "other"):
			frappe.set_user(self.fixture[who])
			boot = frappe._dict()
			extend_bootinfo(boot)
			self.assertEqual(len(boot.dinext_expense_claim_employees), 1)
			self.assertEqual(
				frappe.db.get_value("Employee", boot.dinext_expense_claim_employees[0], "user_id"),
				self.fixture[who],
			)

	def test_workspace_has_exactly_the_20_covered_cards(self):
		workspace = frappe.get_doc("Workspace", "My Timesheets")
		self.assertCountEqual([c.number_card_name for c in workspace.number_cards], self.fixture["expected"])

	def test_expense_section_starts_with_the_total(self):
		workspace = frappe.get_doc("Workspace", "My Timesheets")
		blocks = frappe.parse_json(workspace.content)
		start = next(
			i for i, block in enumerate(blocks) if "My Expense Claims" in block["data"].get("text", "")
		)
		cards = blocks[start + 1 : start + 5]
		self.assertEqual(cards[0]["data"]["number_card_name"], "Total Expense Claims")
		self.assertEqual([(c["type"], c["data"]["col"]) for c in cards], [("number_card", 3)] * 4)

	def test_reopened_source_leaves_approved_population(self):
		name = self.fixture["expected"]["Заявки на отсутствие согласованные мной-1"][0]
		frappe.db.set_value("Application For Leave", name, "status", "Редактирование")
		frappe.set_user(self.fixture["user"])
		from dinext_common.workflow_approval.api import get_legacy_number_card_result

		result = get_legacy_number_card_result(
			{"doc": "Application For Leave", "state": "Согласовано", "route": "application-for-leave"}
		)
		self.assertEqual(result["value"], 0)
		self.assertEqual(
			frappe.get_list("Application For Leave", filters=result["route_options"], pluck="name"), []
		)

	def test_non_open_rounds_are_not_available(self):
		name = self.fixture["expected"]["Заявки на отсутствие у меня на согласовании-2"][0]
		task = frappe.db.get_value(
			"Workflow Task", {"reference_doctype": "Application For Leave", "reference_name": name}, "name"
		)
		from dinext_common.workflow_approval.api import get_legacy_number_card_result

		frappe.set_user(self.fixture["user"])
		for status in ("Stalled", "Conflicted", "Cancelled", "Finalizing", "Transitioned"):
			frappe.db.set_value("Workflow Task", task, "round_status", status)
			result = get_legacy_number_card_result(
				{"doc": "Application For Leave", "state": "На согласовании", "route": "application-for-leave"}
			)
			self.assertEqual(result["value"], 0, status)

	def test_legacy_empty_editing_statuses(self):
		for index, status in enumerate((None, "", "Черновик", "На доработке")):
			fixture.insert(
				"User Timesheet",
				f"NCQA-test-legacy-{index}",
				timesheet_from=self.fixture["user"],
				ts_valid_from="2026-06-01",
				ut_status=status,
			)
		frappe.set_user(self.fixture["user"])
		from frappe.desk.doctype.number_card.number_card import get_result

		card = frappe.get_doc("Number Card", "Моих таймшитов на редактировании")
		self.assertEqual(
			get_result(card, fixture.effective_filters(card, self.fixture["user"], self.fixture["employee"])),
			10,
		)

	def test_daily_percentage_keeps_personal_population(self):
		from frappe.desk.doctype.number_card.number_card import get_percentage_difference, get_result

		fixture.insert(
			"User Timesheet",
			"NCQA-test-recent",
			timesheet_from=self.fixture["user"],
			ts_valid_from="2026-07-01",
			ut_status="Approved",
		)
		frappe.set_user(self.fixture["user"])
		card = frappe.get_doc("Number Card", "Мои согласованные таймшиты")
		filters = fixture.effective_filters(card, self.fixture["user"], self.fixture["employee"])
		self.assertEqual(get_result(card, filters), 2)
		self.assertEqual(get_percentage_difference(card.as_dict(), filters, 2), 100)

	def test_other_source_without_task_is_excluded(self):
		name = self.fixture["expected"]["Заявки на отсутствие у меня на согласовании-2"][0]
		frappe.db.delete(
			"Workflow Task", {"reference_doctype": "Application For Leave", "reference_name": name}
		)
		frappe.set_user(self.fixture["user"])
		from dinext_common.workflow_approval.api import get_legacy_number_card_result

		self.assertEqual(
			get_legacy_number_card_result(
				{"doc": "Application For Leave", "state": "На согласовании", "route": "application-for-leave"}
			)["value"],
			0,
		)

	def test_pending_approvals_require_a_mandatory_target_regardless_of_ownership(self):
		from dinext_common.workflow_approval.api import get_legacy_number_card_result

		frappe.set_user(self.fixture["user"])
		for name in (
			"ТШ у меня на согласовании-2",
			"Заявки на отсутствие у меня на согласовании-2",
			"Заявок EC у меня на согласовании",
		):
			with self.subTest(card=name):
				filters = frappe.db.get_value("Number Card", name, "filters_json")
				result = get_legacy_number_card_result(filters)
				expected = self.fixture["expected"][name]
				self.assertEqual(result["value"], len(expected))
				self.assertCountEqual(result["route_options"]["name"][1], expected)

	def test_workflow_self_approval_rule_controls_eligible_actors(self):
		from dinext_common.workflow_approval.engine import _eligible_approvers

		name = self.fixture["expected"]["Моих Заявок на согласовании"][0]
		source = frappe.get_doc("Application For Leave", name)
		self.assertEqual(source.owner, self.fixture["user"])
		transition = frappe._dict(allowed="NCQA-test-Reader", allow_self_approval=0, condition="")
		self.assertNotIn(self.fixture["user"], _eligible_approvers(source, transition))
		transition.allow_self_approval = 1
		self.assertIn(self.fixture["user"], _eligible_approvers(source, transition))

	def test_cancelled_expense_leaves_both_personal_and_approval_cards(self):
		name = self.fixture["expected"]["Заявок EC Согласовано"][0]
		frappe.db.set_value("Expense Claim", name, "docstatus", 2)
		frappe.set_user(self.fixture["user"])
		rows = {r["card"]: r for r in fixture.evaluate(self.fixture)}
		total = rows["Всего заявок на расходы"]
		self.assertEqual(total["value"], 3)
		self.assertCountEqual(total["names"], set(total["expected"]) - {name})
		for card in ("Заявок EC Согласовано", "Заявок EC Согласованных мной"):
			self.assertEqual(rows[card]["value"], 0)
			self.assertEqual(rows[card]["names"], [])

	def test_previous_round_decision_is_not_current_approval(self):
		from dinext_common.tests.ui_test_helpers import _manual_task

		name = self.fixture["expected"]["Заявок EC Согласованных мной"][0]
		new = _manual_task(
			doctype="Expense Claim",
			name=name,
			workflow="Expense_Claim_Workflow",
			state="На согласовании",
			approver=self.fixture["other"],
			round_status="Transitioned",
			status="Completed",
			round_id=frappe.generate_hash(length=40),
		)
		frappe.db.set_value("Workflow Task", new, {"next_state": "Согласовано", "source_title": name})
		frappe.set_user(self.fixture["user"])
		from dinext_common.workflow_approval.api import get_legacy_number_card_result

		self.assertEqual(
			get_legacy_number_card_result(
				{"doc": "Expense Claim", "state": "Согласовано", "route": "expense-claim"}
			)["value"],
			0,
		)

	def test_source_permission_revocation_removes_approval(self):
		name = self.fixture["expected"]["Заявок EC Согласованных мной"][0]
		frappe.db.delete("Has Role", {"parent": self.fixture["user"], "role": "NCQA-test-Reader"})
		frappe.clear_cache(user=self.fixture["user"])
		frappe.set_user(self.fixture["user"])
		self.assertFalse(frappe.has_permission("Expense Claim", "read", doc=name))
		from dinext_common.workflow_approval.api import get_legacy_number_card_result

		self.assertEqual(
			get_legacy_number_card_result(
				{"doc": "Expense Claim", "state": "Согласовано", "route": "expense-claim"}
			)["value"],
			0,
		)

	def test_deleted_source_does_not_break_approval_card(self):
		name = self.fixture["expected"]["Заявок EC Согласованных мной"][0]
		frappe.db.delete("Expense Claim", {"name": name})
		frappe.set_user(self.fixture["user"])
		from dinext_common.workflow_approval.api import get_legacy_number_card_result

		self.assertEqual(
			get_legacy_number_card_result(
				{"doc": "Expense Claim", "state": "Согласовано", "route": "expense-claim"}
			)["value"],
			0,
		)

	def test_standard_permissions_survive_fixture_role(self):
		for dt in ("Workspace", "Number Card", "Timesheet Settings"):
			self.assertFalse(frappe.db.exists("Custom DocPerm", {"parent": dt, "role": ["like", "NCQA-%"]}))
			standard = {
				(r.role, r.permlevel)
				for r in frappe.get_all("DocPerm", filters={"parent": dt}, fields=["role", "permlevel"])
			}
			active = {(r.role, r.permlevel) for r in frappe.get_meta(dt).permissions}
			self.assertTrue(standard.issubset(active), dt)

	def test_cancelled_round_decision_is_not_current_approval(self):
		name = self.fixture["expected"]["Заявок EC Согласованных мной"][0]
		frappe.db.set_value(
			"Workflow Task",
			{"reference_doctype": "Expense Claim", "reference_name": name},
			"round_status",
			"Cancelled",
		)
		frappe.set_user(self.fixture["user"])
		from dinext_common.workflow_approval.api import get_legacy_number_card_result

		self.assertEqual(
			get_legacy_number_card_result(
				{"doc": "Expense Claim", "state": "Согласовано", "route": "expense-claim"}
			)["value"],
			0,
		)

	def test_archived_decision_is_not_reused_for_restored_name(self):
		name = self.fixture["expected"]["Заявок EC Согласованных мной"][0]
		frappe.db.set_value(
			"Workflow Task",
			{"reference_doctype": "Expense Claim", "reference_name": name},
			"source_deleted_at",
			frappe.utils.now_datetime(),
		)
		frappe.set_user(self.fixture["user"])
		from dinext_common.workflow_approval.api import get_legacy_number_card_result

		self.assertEqual(
			get_legacy_number_card_result(
				{"doc": "Expense Claim", "state": "Согласовано", "route": "expense-claim"}
			)["value"],
			0,
		)

	def test_canonical_workflow_state_must_agree_with_display_status(self):
		name = self.fixture["expected"]["Заявки на отсутствие согласованные мной-1"][0]
		frappe.db.set_value("Application For Leave", name, "workflow_state", "Редактирование")
		frappe.set_user(self.fixture["user"])
		from dinext_common.workflow_approval.api import get_legacy_number_card_result

		self.assertEqual(
			get_legacy_number_card_result(
				{"doc": "Application For Leave", "state": "Согласовано", "route": "application-for-leave"}
			)["value"],
			0,
		)

	def test_zz_cleanup_removes_users_credentials_and_fixture_grants(self):
		auth = frappe.qb.Table("__Auth")
		user = self.fixture["user"]
		query = frappe.qb.from_(auth).select(auth.name).where((auth.doctype == "User") & (auth.name == user))
		self.assertTrue(query.run())
		fixture.cleanup("test")
		self.assertFalse(query.run())
		self.assertFalse(frappe.db.exists("User", user))
		for kind in ("DocPerm", "Custom DocPerm"):
			self.assertFalse(frappe.db.exists(kind, {"role": "NCQA-test-Reader"}))
