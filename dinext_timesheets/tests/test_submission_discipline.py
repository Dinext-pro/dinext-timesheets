import unittest


class TestSubmissionDiscipline(unittest.TestCase):
	def test_first_submission_result_is_not_replaced_by_resubmission(self):
		from dinext_timesheets.submission_discipline import submission_result

		events = [
			dict(submitted_at="2026-11-09 16:00:00", submission_deadline="2026-11-09", first_submission=1),
			dict(submitted_at="2026-11-12 16:00:00", submission_deadline="2026-11-10", first_submission=0),
		]
		result = submission_result(events, today="2026-11-13", current_deadline="2026-11-10")
		self.assertEqual(result["status"], "On Time")
		self.assertEqual(result["actual"], "2026-11-09 16:00:00")
		self.assertEqual(result["deadline"], "2026-11-09")
		self.assertEqual(result["resubmissions"], 1)

	def test_unknown_history_never_uses_modified_time(self):
		from dinext_timesheets.submission_discipline import submission_result

		result = submission_result(
			[], today="2026-11-13", current_deadline="2026-11-10", current_status="Approved"
		)
		self.assertEqual(result["status"], "Unknown")
		self.assertIsNone(result["actual"])

	def test_historical_rework_without_first_event_is_unknown(self):
		from dinext_timesheets.submission_discipline import submission_result

		result = submission_result(
			[],
			today="2026-11-13",
			current_deadline="2026-11-10",
			current_status="Rework",
			history_tracked=False,
		)
		self.assertEqual(result["status"], "Unknown")

	def test_historical_submission_requires_version_and_complete_assignment_evidence(self):
		from dinext_timesheets.submission_history import proven_submission

		versions = [
			dict(
				name="first",
				creation="2026-11-09 10:00:00",
				owner="author",
				data={"changed": [["ut_status", "Draft", "Pending Approval"]]},
			),
			dict(
				name="later",
				creation="2026-11-12 10:00:00",
				owner="author",
				data={"changed": [["ts_date_of_dispatch", "2026-11-09", "2026-11-12"]]},
			),
		]
		positions = [dict(name="position", creation="2026-11-02 10:00:00")]
		tasks = [
			dict(reference_name="position", workflow_state="Pending Approval", creation="2026-11-09 09:59:00")
		]
		result = proven_submission(versions, positions, tasks, current_deadline="2026-11-12")
		self.assertEqual(result["at"], "2026-11-09 10:00:00")
		self.assertEqual(result["deadline"], "2026-11-09")
		self.assertIsNone(proven_submission(versions, positions, [], current_deadline="2026-11-12"))
