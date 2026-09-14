/**
 * Form-level buttons / post-mount hooks (copy, WF, submit, limits, readonly, dashboard).
 */
import { canEdit, canReprocessJournalEntries } from "./model.js";
import { setupCopyButtons } from "./copy.js";
import { processUTWorkflow } from "./workflow.js";
import { refreshLimits } from "./limits.js";
import { setupSubmitButtons } from "./submit.js";
import { applyToolbarChrome } from "./toolbar.js";
import { showTimesheetDashboard } from "./dashboard.js";
import { resolveTeamLeadAccess } from "./team_lead.js";
import { applyNewTimesheetDefaults } from "./new_doc.js";
import { applyTimesheetSidebarHide } from "./sidebar.js";
import { scheduleCascadeLayout } from "./column-layout.js";

const REPROCESS_LABEL = "Перепровести";
const REPROCESS_GROUP = "Фин. проводки";

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

/** V10 disableReprocessJournalEntries: only Согласован + UT import perm. */
function applyReprocessJournalEntriesButton(frm) {
	frm.remove_custom_button(__(REPROCESS_LABEL), __(REPROCESS_GROUP));
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
	applyNewTimesheetDefaults(frm);
	if (frm.is_new() || frm.doc?.__islocal) {
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
			setupCopyButtons(frm);
			setupSubmitButtons(frm);
			if (frm.ut?.table) {
				await refreshLimits(frm);
			}
		} finally {
			frm._ut_chrome_inflight = false;
		}
	}
	applyReprocessJournalEntriesButton(frm);
	await processUTWorkflow(frm);
	await showTimesheetDashboard(frm);
	scheduleCascadeLayout(frm);
}
