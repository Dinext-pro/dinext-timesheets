/**
 * Form-level buttons / post-mount hooks (copy, WF, submit, limits, readonly, dashboard).
 */
import { canEdit, canReprocessJournalEntries } from "./model.js";
import { setupCopyButtons, disableCopyButtons } from "./copy.js";
import { processUTWorkflow, clearWorkflowButtons } from "./workflow.js";
import { refreshLimits } from "./limits.js";
import { setupSubmitButtons, clearSubmitButtons } from "./submit.js";
import { resetTimesheetRuntime } from "./state.js";
import { applyToolbarChrome } from "./toolbar.js";
import { showTimesheetDashboard } from "./dashboard.js";
import { resolveTeamLeadAccess } from "./team_lead.js";
import { applyNewTimesheetDefaults } from "./new_doc.js";
import { applyTimesheetSidebarHide } from "./sidebar.js";
import { scheduleCascadeLayout } from "./column-layout.js";

const REPROCESS_LABEL = "Reprocess";
const REPROCESS_GROUP = "Financial Entries";

function applyReadonlyChrome(frm) {
	if (canEdit(frm)) {
		frm.enable_save();
	} else {
		frm.disable_save();
	}
	if (frm.ut?.table) {
		const editable = canEdit(frm);
		frm.ut.table.setOption?.("edit", editable);
		frm.ut.table.setOption?.("clipboard", { enabled: editable });
		frm.ut.table.setOption?.("fillHandle", { enabled: editable });
		applyToolbarChrome(frm);
	}
}

function clearReprocessButton(frm) {
	frm.remove_custom_button(__(REPROCESS_LABEL), __(REPROCESS_GROUP));
	frm.remove_custom_button(REPROCESS_LABEL, REPROCESS_GROUP);
}

function clearTimesheetButtons(frm) {
	disableCopyButtons(frm);
	clearSubmitButtons(frm);
	clearWorkflowButtons(frm);
	clearReprocessButton(frm);
}

/** V10 disableReprocessJournalEntries: only Согласован + UT import perm. */
function applyReprocessJournalEntriesButton(frm) {
	clearReprocessButton(frm);
	if (frm.doc.ut_status !== "Согласован" || !canReprocessJournalEntries()) {
		return;
	}
	frm.add_custom_button(
		__(REPROCESS_LABEL),
		async () => {
			await frappe.call({
				method: "process_journal_entries_for_timesheet",
				args: { doc: frm.doc },
				freeze: true,
			});
			frm.reload_doc();
		},
		__(REPROCESS_GROUP)
	);
}

export async function setupFormChrome(frm) {
	if (!frm) {
		return;
	}
	applyTimesheetSidebarHide();
	if (frm.is_new() || frm.doc?.__islocal) {
		resetTimesheetRuntime(frm);
		clearTimesheetButtons(frm);
		applyNewTimesheetDefaults(frm);
		return;
	}
	const chromeKey = [frm.doc.name, frm.doc.modified, frm.doc.ut_status].join(":");
	const skipHeavy =
		frm._ut_chrome_ready === chromeKey || frm._ut_chrome_inflight;
	if (!skipHeavy) {
		frm._ut_chrome_inflight = true;
		frm._ut_chrome_ready = chromeKey;
		try {
			await resolveTeamLeadAccess(frm);
			applyReadonlyChrome(frm);
			if (frm.ut?.table) {
				await refreshLimits(frm);
			}
		} finally {
			frm._ut_chrome_inflight = false;
		}
	}
	setupCopyButtons(frm);
	setupSubmitButtons(frm);
	applyReprocessJournalEntriesButton(frm);
	await processUTWorkflow(frm);
	await showTimesheetDashboard(frm);
	scheduleCascadeLayout(frm);
}
