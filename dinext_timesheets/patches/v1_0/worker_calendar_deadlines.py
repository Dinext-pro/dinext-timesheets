"""Configure deadline metadata without backfilling existing timesheet dates."""
from dinext_timesheets.setup.deadlines import configure_deadline_metadata


def execute():
	configure_deadline_metadata()
