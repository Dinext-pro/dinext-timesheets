# ruff: noqa: RUF001 -- exact legacy metadata labels
"""Migrate the My Timesheets Workspace without replacing site customizations."""

import frappe

from dinext_common.setup.personal_workspace import localize_workspace
from dinext_timesheets.patches.v1_0 import refresh_personal_workspace


LEGACY_DEFAULT_MODIFIED = "2026-10-15 02:06:03.778584"

def execute():
	legacy_name = "Мои Таймшиты"
	name = "My Timesheets"
	if (
		not frappe.db.exists("Workspace", name)
		and str(frappe.db.get_value("Workspace", legacy_name, "modified")) == LEGACY_DEFAULT_MODIFIED
		and not frappe.db.exists("Patch Log", {"patch": refresh_personal_workspace.__name__})
	):
		refresh_personal_workspace.execute()

	localize_workspace(
		legacy_name,
		name,
		headings={
			'Мои Заявки на расходы': 'My Expense Claims',
			'Мои Заявки на отсутствие': 'My Leave Applications',
			'Мои согласования:': 'My Approvals',
			'По Таймшитам': 'Timesheet Approvals',
			'По Заявкам на отсутствие': 'Leave Approvals',
			'По Заявкам на расходы': 'Expense Approvals',
			'Отчетность': 'Timesheet Reports',
			'Настройки': 'Timesheet Configuration',
		},
		widgets={
			'таймшитов всего': 'Total Timesheets',
			'тш на редактировании': 'Timesheets in Editing',
			'тш на согласовании': 'Timesheets Pending Approval',
			'тш отклонено': 'Rejected Timesheets',
			'тш просрочено': 'Overdue Timesheets',
			'тш согласовано': 'Approved Timesheets',
			'Всего заявок на расходы': 'Total Expense Claims',
			'из них на согласовании': 'Expense Claims Pending Approval',
			'из них согласовано': 'Approved Expense Claims',
			'из них отклонено': 'Rejected Expense Claims',
			'заявок всего': 'Total Leave Applications',
			'заявок на согласовании': 'Leave Applications Pending Approval',
			'заявок согласовано': 'Approved Leave Applications',
			'заявок отклонено': 'Rejected Leave Applications',
			'ТШ у меня на согласовании': 'Timesheets Awaiting My Approval',
			'Заявки у меня на согласовании': 'Leave Applications Awaiting My Approval',
			'Расходы у меня на согласовании': 'Expenses Awaiting My Approval',
			'ТШ согласованные мной': 'Timesheets Approved by Me',
			'Заявки согласованные мной': 'Leave Applications Approved by Me',
			'Расходы согласованные мной': 'Expenses Approved by Me',
			'Мои списания по ТШ': 'My Logged Timesheet Hours',
			'Отчетность по ТШ': 'Timesheet Report',
			'Отчет по утилизации': 'Utilization Report',
			'Календарь отсутствий': 'Leave Calendar',
		},
	)
