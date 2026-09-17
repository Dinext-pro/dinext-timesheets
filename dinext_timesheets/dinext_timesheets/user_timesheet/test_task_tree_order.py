# Copyright (c) 2026, Dinext and contributors
"""Unit tests for UT task picker tree order (ISS-2026-00926)."""

from __future__ import annotations

import unittest

from dinext_timesheets.dinext_timesheets.user_timesheet.tasks import structure_project_tasks


def _task(name, parent=None, lft=0, subject=None):
    return {
        "name": name,
        "subject": subject or name,
        "parent_task": parent,
        "lft": lft,
    }


class TestStructureProjectTasks(unittest.TestCase):
    def test_child_after_parent_despite_modified_order(self):
        rows = [
            _task("child", parent="parent", lft=2, subject="подзадача1.1.1"),
            _task("parent", lft=1, subject="Пилотное"),
            _task("sib-late", parent="parent", lft=6, subject="Подзадача1.2.2"),
            _task("sib-mid", parent="parent", lft=4, subject="Подзадача1.3.3"),
        ]
        ordered = structure_project_tasks(rows)
        self.assertEqual([t["name"] for t in ordered], ["parent", "child", "sib-mid", "sib-late"])
        self.assertEqual([t["level"] for t in ordered], [0, 1, 1, 1])
        self.assertTrue(all("lft" not in t for t in ordered))

    def test_grandchild_nested(self):
        rows = [
            _task("gc", parent="child", lft=3),
            _task("child", parent="parent", lft=2),
            _task("parent", lft=1),
        ]
        ordered = structure_project_tasks(rows)
        self.assertEqual([t["name"] for t in ordered], ["parent", "child", "gc"])
        self.assertEqual([t["level"] for t in ordered], [0, 1, 2])

    def test_missing_parent_is_root_by_lft(self):
        rows = [
            _task("other-root", lft=10),
            _task("orphan", parent="gone", lft=3),
        ]
        ordered = structure_project_tasks(rows)
        self.assertEqual([t["name"] for t in ordered], ["orphan", "other-root"])
        self.assertEqual([t["level"] for t in ordered], [0, 0])
