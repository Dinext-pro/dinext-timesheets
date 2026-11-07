/**
 * Form dashboard: pending approvers, overdue, Journal Entry connections.
 *
 * No dashboard.reset() here: it hides Connections and races refresh.
 * Replace only messages owned by this dashboard.
 * JE link lives on DocType (`custom_user_timesheet`). Do not add_transactions
 * or refresh(): both duplicate the badge; refresh() also reset()s.
 */
const PENDING_APPROVERS =
	"dinext_common.workflow_approval.api.get_pending_approvers";
const REBUILD_ROUNDS =
	"dinext_timesheets.workflow_approval.get_timesheet_rebuild_rounds";
const APPROVALS_CSS = "/assets/dinext_timesheets/css/timesheet_approvals.css";
const APPROVER_TITLE_COLUMNS = ["project_label", "document_label", "project_role"];

export async function showTimesheetDashboard(frm) {
	if (!frm?.dashboard) {
		return;
	}

	const requested = {
		doctype: frm.doc?.doctype || frm.doctype,
		name: frm.doc?.name,
		route: frappe.get_route_str(),
		generation: (frm._ut_dash_gen = (frm._ut_dash_gen || 0) + 1),
	};
	const comments = frappe.dinext.refreshWorkflowComments(frm);
	frappe.dinext.paintPendingApprovers(frm, []);
	applyPositionApproverTitles(frm, []);
	paintDeadline(frm);
	frappe.dinext?.paintRebuildRounds?.(frm.dashboard, [], rebuildOptions(frm));
	applyJournalEntryConnections(frm);
	if (frm.is_new() || !requested.name) return;

	frappe.require(APPROVALS_CSS);
	await Promise.all([loadPendingApprovers(frm, requested), comments]);
	if (!isCurrentRequest(frm, requested)) return;

	const deadlineState = await frappe.dinext
		.workflowRequest("dinext_timesheets.deadlines.get_deadline_state", {
			name: requested.name,
		})
		.catch(() => null);
	if (!isCurrentRequest(frm, requested)) return;
	paintDeadline(frm, deadlineState);
	await showRebuildRounds(frm, requested);
}

function isCurrentRequest(frm, requested) {
	return (
		requested.generation === frm._ut_dash_gen &&
		requested.doctype === (frm.doc?.doctype || frm.doctype) &&
		requested.name === frm.doc?.name &&
		requested.route === frappe.get_route_str()
	);
}

function paintDeadline(frm, state) {
	frm.layout?.message?.find(".dinext-timesheet-deadline").remove();
	if (!state?.overdue) return;
	frm.dashboard.add_comment(
		__("Timesheet is overdue. Submission deadline: {0}", [
			frappe.datetime.str_to_user(state.deadline),
		]),
		"orange",
		true
	);
	frm.layout?.message
		?.children(".form-message.orange")
		.last()
		.addClass("dinext-timesheet-deadline");
}

function rebuildOptions(frm) {
	return {
		fullWidth: true,
		container: frm.page?.wrapper?.find(".page-body").first(),
		reload: () => frm.reload_doc(),
	};
}

async function showRebuildRounds(frm, requested) {
	if (!isCurrentRequest(frm, requested)) return;
	const rounds = await frappe.dinext
		.workflowRequest(REBUILD_ROUNDS, { timesheet_name: requested.name })
		.catch(() => []);
	if (!isCurrentRequest(frm, requested)) return;
	const positions = new Set((rounds || []).map((round) => round.reference_name));
	frappe.dinext?.paintRebuildRounds?.(frm.dashboard, rounds || [], {
		...rebuildOptions(frm),
		message: __("Approval needs rebuilding for {0} positions", [positions.size]),
	});
}

function applyPositionApproverTitles(frm, rows) {
	const byPosition = new Map();
	for (const row of rows || []) {
		if (!row?.reference_name) {
			continue;
		}
		const key = String(row.reference_name);
		const bucket = byPosition.get(key) || [];
		bucket.push(row);
		byPosition.set(key, bucket);
	}
	for (const gridRow of frm.ut?.rows || []) {
		if (gridRow?.rowType !== "position") {
			continue;
		}
		const names = frappe.dinext.getPendingApproverNames(
			byPosition.get(String(gridRow.id)) || []
		);
		gridRow.approver_tooltip = names.length ? frappe.utils.comma_and(names) : "";
	}
	frm.ut?.table?.api?.refreshCells?.({
		columns: APPROVER_TITLE_COLUMNS,
		force: true,
	});
}

async function loadPendingApprovers(frm, requested) {
	const rows = await frappe.dinext
		.workflowRequest(PENDING_APPROVERS, {
			doctype: requested.doctype,
			name: requested.name,
		})
		.catch(() => []);
	if (!isCurrentRequest(frm, requested)) return;

	applyPositionApproverTitles(frm, rows || []);
	frappe.dinext.paintPendingApprovers(frm, rows || []);
}

/** Show DocType Connections only when Согласован + can_read(Journal Entry). */
function applyJournalEntryConnections(frm) {
	const allow =
		frm.doc?.ut_status === "Approved" && !!frappe.model.can_read?.("Journal Entry");

	if (!allow) {
		document.body.classList.remove("ut-show-connections");
		frm.dashboard.links_area?.hide?.();
		return;
	}

	document.body.classList.add("ut-show-connections");
	frm.dashboard.links_area?.show?.();
}
