"""Keep the status mirror in sync for the old position schema."""

from ..status import has_legacy_position_status


def sync_status_from_workflow_state(doc) -> None:
	if not has_legacy_position_status():
		return
	from dinext_timesheets.workflow_scenario_actions import uses_local_scenarios

	if uses_local_scenarios():
		from dinext_common.workflow_approval.scenarios import service

		if service.get_context(doc).get("state_field") != "workflow_state":
			return
	doc.status = doc.workflow_state
