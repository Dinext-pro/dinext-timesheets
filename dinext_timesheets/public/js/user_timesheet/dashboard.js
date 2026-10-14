/**
 * Form dashboard: pending approvers, overdue, Journal Entry connections.
 *
 * No dashboard.reset() here: it hides Connections and races refresh.
 * add_comment appends headlines — clear first, apply once.
 * JE link lives on DocType (`custom_user_timesheet`). Do not add_transactions
 * or refresh(): both duplicate the badge; refresh() also reset()s.
 */
const PENDING_APPROVERS =
	"dinext_common.workflow_approval.api.get_pending_approvers";
const APPROVALS_CSS = "/assets/dinext_timesheets/css/timesheet_approvals.css";
const APPROVER_TITLE_COLUMNS = ["project_label", "document_label", "project_role"];

export async function showTimesheetDashboard(frm) {
	if (!frm?.dashboard || frm.is_new()) {
		return;
	}

	frappe.require(APPROVALS_CSS);

	const gen = (frm._ut_dash_gen = (frm._ut_dash_gen || 0) + 1);
	const headline = await loadPendingApprovers(frm, gen);
	if (gen !== frm._ut_dash_gen) {
		return;
	}

	const comments = [];
	if (headline) {
		comments.push({ text: headline, color: "blue" });
	}
	if (
		frm.doc.is_overdue &&
		(frm.doc.ut_status === "Черновик" || frm.doc.ut_status === "На доработке")
	) {
		comments.push({
			text: __("Timesheet is overdue! Submit positions for approval immediately!"),
			color: "orange",
		});
	}

	if (gen !== frm._ut_dash_gen) {
		return;
	}

	frm.dashboard.clear_headline?.();
	for (const item of comments) {
		frm.dashboard.add_comment(item.text, item.color, true);
	}

	applyJournalEntryConnections(frm);
}

function uniqueApproverNames(rows, excludeSession) {
	const session = frappe.session?.user;
	const byId = new Map();
	for (const row of rows || []) {
		if (!row?.approver) {
			continue;
		}
		if (excludeSession && session && row.approver === session) {
			continue;
		}
		if (!byId.has(row.approver)) {
			byId.set(row.approver, row.approver_name || row.approver);
		}
	}
	return [...byId.values()].sort((left, right) => String(left).localeCompare(String(right)));
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
		const names = uniqueApproverNames(byPosition.get(String(gridRow.id)) || [], true);
		gridRow.approver_tooltip = names.length ? frappe.utils.comma_and(names) : "";
	}
	frm.ut?.table?.api?.refreshCells?.({
		columns: APPROVER_TITLE_COLUMNS,
		force: true,
	});
}

async function loadPendingApprovers(frm, gen) {
	const dashboard = frm.dashboard.wrapper || frm.dashboard.parent;
	dashboard?.find?.(".dinext-pending-approvers")?.remove?.();
	if (frm.is_new() || !frm.doc?.name) {
		applyPositionApproverTitles(frm, []);
		return "";
	}

	const rows = await frappe
		.xcall(PENDING_APPROVERS, {
			doctype: frm.doctype,
			name: frm.doc.name,
		})
		.catch(() => []);
	if (gen !== frm._ut_dash_gen) {
		return "";
	}

	applyPositionApproverTitles(frm, rows || []);
	const names = uniqueApproverNames(rows || [], true).map((name) =>
		frappe.utils.escape_html(name)
	);
	if (!names.length) {
		return "";
	}
	return __("Action expected from: {0}", [frappe.utils.comma_and(names)]);
}

/** Show DocType Connections only when Согласован + can_read(Journal Entry). */
function applyJournalEntryConnections(frm) {
	const allow =
		frm.doc.ut_status === "Согласован" && !!frappe.model.can_read?.("Journal Entry");

	if (!allow) {
		document.body.classList.remove("ut-show-connections");
		frm.dashboard.links_area?.hide?.();
		return;
	}

	document.body.classList.add("ut-show-connections");
	frm.dashboard.links_area?.show?.();
}
