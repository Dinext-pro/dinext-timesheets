import unittest

from dinext_timesheets.workflow_approval import _duplicate_position_lines


class TestSubmissionPositionDuplicates(unittest.TestCase):
	def test_complete_row_matches_project_role_type_and_document(self):
		line = dict(project="P", project_role="BA", document_type="Task", document_name="T1")
		rows = [line, {**line, "project_role": "QA"}, {**line, "document_type": "Issue"}]
		self.assertEqual(_duplicate_position_lines(rows), [])
		self.assertEqual(_duplicate_position_lines([*rows, line]), [[1, 4]])
