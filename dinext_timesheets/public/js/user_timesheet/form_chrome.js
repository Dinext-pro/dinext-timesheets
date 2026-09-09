/**
 * Form-level buttons / post-mount hooks (copy, WF, submit, limits, readonly, dashboard).
 */
import { canEdit } from "./model.js";
import { setupCopyButtons } from "./copy.js";
import { processUTWorkflow } from "./workflow.js";
import { refreshLimits } from "./limits.js";
import { setupSubmitButtons } from "./submit.js";
import { applyToolbarChrome } from "./toolbar.js";
import { showTimesheetDashboard } from "./dashboard.js";
import { resolveTeamLeadAccess } from "./team_lead.js";
import { applyNewTimesheetDefaults } from "./new_doc.js";

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

export async function setupFormChrome(frm) {
	if (!frm) {
		return;
	}
	applyNewTimesheetDefaults(frm);
	if (frm.is_new() || frm.doc?.__islocal) {
		return;
	}
	const chromeKey = [frm.doc.name, frm.doc.modified, frm.doc.ut_status].join(":");
	if (frm._ut_chrome_ready === chromeKey || frm._ut_chrome_inflight) {
		return;
	}
	frm._ut_chrome_inflight = true;
	frm._ut_chrome_ready = chromeKey;
	try {
		await resolveTeamLeadAccess(frm);
		applyReadonlyChrome(frm);
		setupCopyButtons(frm);
		setupSubmitButtons(frm);
		await processUTWorkflow(frm);
		await showTimesheetDashboard(frm);
		if (frm.ut?.table) {
			await refreshLimits(frm);
		}
	} finally {
		frm._ut_chrome_inflight = false;
	}
}
