def execute():
	from dinext_timesheets.setup.workflow_deadlines import configure_utp_deadlines

	configure_utp_deadlines()
	from dinext_timesheets.submission_history import backfill_submission_events

	backfill_submission_events()
