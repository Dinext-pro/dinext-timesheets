# Copyright (c) 2026, Dinext and contributors
"""Unit tests for UTP → Task act_* / UT rollup (ISS-2026-03288 layer 3)."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from frappe.utils import getdate

from dinext_timesheets.dinext_timesheets.user_timesheet.events.status_rollup import (
	_update_task_act_dates,
	rollup_ut_status_and_task_dates,
)


class _Doc:
	def __init__(self, **kwargs):
		self.__dict__.update(kwargs)

	def get(self, key, default=None):
		return getattr(self, key, default)

	def get_doc_before_save(self):
		return self._old


class TestRollupTriggers(unittest.TestCase):
	@patch(
		"dinext_timesheets.dinext_timesheets.user_timesheet.events.status_rollup._update_task_act_dates"
	)
	@patch(
		"dinext_timesheets.dinext_timesheets.user_timesheet.events.status_rollup._maybe_approve_ut"
	)
	def test_enter_approved_updates_task_dates(self, approve, update_dates):
		doc = _Doc(
			status="Согласовано",
			document_type="Task",
			document_name="TASK-1",
			user_timesheet="UT-1",
		)
		doc._old = _Doc(status="Редактирование")
		rollup_ut_status_and_task_dates(doc)
		approve.assert_called_once_with("UT-1")
		update_dates.assert_called_once_with(doc)

	@patch(
		"dinext_timesheets.dinext_timesheets.user_timesheet.events.status_rollup._update_task_act_dates"
	)
	def test_other_status_skips_task_dates(self, update_dates):
		doc = _Doc(
			status="Редактирование",
			document_type="Task",
			document_name="TASK-1",
			user_timesheet="UT-1",
		)
		doc._old = _Doc(status="Редактирование")
		rollup_ut_status_and_task_dates(doc)
		update_dates.assert_not_called()


class TestActDates(unittest.TestCase):
	@patch("dinext_timesheets.dinext_timesheets.user_timesheet.events.status_rollup.frappe.get_doc")
	@patch("dinext_timesheets.dinext_timesheets.user_timesheet.events.status_rollup.frappe.get_all")
	def test_expands_act_from_approved_hours(self, get_all, get_doc):
		get_all.return_value = [SimpleNamespace(name="UTP-1")]
		utp = MagicMock()
		utp.get.return_value = [
			SimpleNamespace(date="2026-08-01", hours=2),
			SimpleNamespace(date="2026-08-10", hours=1),
		]
		task = MagicMock()
		task.act_start_date = None
		task.act_end_date = None
		task.completed_on = None
		task.get.side_effect = lambda k, d=None: None
		get_doc.side_effect = [utp, task]

		doc = _Doc(document_name="TASK-1")
		_update_task_act_dates(doc)

		self.assertEqual(getdate(task.act_start_date), getdate("2026-08-01"))
		self.assertEqual(getdate(task.act_end_date), getdate("2026-08-10"))
		task.save.assert_called_once()

	@patch("dinext_timesheets.dinext_timesheets.user_timesheet.events.status_rollup.frappe.get_doc")
	@patch("dinext_timesheets.dinext_timesheets.user_timesheet.events.status_rollup.frappe.get_all")
	def test_does_not_shrink_existing_act(self, get_all, get_doc):
		get_all.return_value = [SimpleNamespace(name="UTP-1")]
		utp = MagicMock()
		utp.get.return_value = [SimpleNamespace(date="2026-08-05", hours=2)]
		task = MagicMock()
		task.act_start_date = "2026-08-01"
		task.act_end_date = "2026-08-20"
		task.completed_on = None
		task.get.side_effect = lambda k, d=None: None
		get_doc.side_effect = [utp, task]

		_update_task_act_dates(_Doc(document_name="TASK-1"))
		task.save.assert_not_called()

	@patch("dinext_timesheets.dinext_timesheets.user_timesheet.events.status_rollup.frappe.get_doc")
	@patch("dinext_timesheets.dinext_timesheets.user_timesheet.events.status_rollup.frappe.get_all")
	def test_empty_approved_does_not_clear_act(self, get_all, get_doc):
		get_all.return_value = []
		task = MagicMock()
		task.act_start_date = "2026-08-01"
		task.act_end_date = "2026-08-10"
		task.completed_on = None
		task.get.side_effect = lambda k, d=None: None
		get_doc.return_value = task

		_update_task_act_dates(_Doc(document_name="TASK-1"))
		task.save.assert_not_called()

	@patch("dinext_timesheets.dinext_timesheets.user_timesheet.events.status_rollup.frappe.get_meta")
	@patch("dinext_timesheets.dinext_timesheets.user_timesheet.events.status_rollup.frappe.db.get_value")
	@patch("dinext_timesheets.dinext_timesheets.user_timesheet.events.status_rollup.frappe.get_doc")
	@patch("dinext_timesheets.dinext_timesheets.user_timesheet.events.status_rollup.frappe.get_all")
	def test_sla_resolution_widens_act_end(self, get_all, get_doc, db_get_value, get_meta):
		get_all.return_value = [SimpleNamespace(name="UTP-1")]
		utp = MagicMock()
		utp.get.return_value = [SimpleNamespace(date="2026-08-05", hours=2)]
		task = MagicMock()
		task.act_start_date = None
		task.act_end_date = None
		task.completed_on = None
		task.get.side_effect = lambda k, d=None: (
			"Issue" if k == "type" else "ISS-1" if k == "custom_linked_issue" else None
		)
		get_doc.side_effect = [utp, task]
		meta = MagicMock()
		meta.has_field.side_effect = lambda name: name == "sla_resolution_date"
		get_meta.return_value = meta
		db_get_value.return_value = {
			"opening_date": "2026-08-01",
			"sla_resolution_date": "2026-08-20",
		}

		_update_task_act_dates(_Doc(document_name="TASK-1"))
		self.assertEqual(getdate(task.act_end_date), getdate("2026-08-20"))
		task.save.assert_called_once()


if __name__ == "__main__":
	unittest.main()
