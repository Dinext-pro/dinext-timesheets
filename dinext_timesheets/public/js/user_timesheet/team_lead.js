/**
 * Current team lead for User Group on date (demodev getCurrentTeamLead).
 */
export async function getCurrentTeamLead(userGroup, targetDateStr) {
	if (!userGroup || !targetDateStr) {
		return null;
	}
	try {
		const doc = await frappe.db.get_doc("User Group", userGroup);
		const rows = doc?.custom_table || [];
		if (!rows.length) {
			return null;
		}
		const target = frappe.datetime.str_to_obj(targetDateStr);
		let last = null;
		for (const row of rows) {
			if (!row.date) {
				continue;
			}
			const assignmentDate = frappe.datetime.str_to_obj(row.date);
			if (assignmentDate <= target) {
				if (!last || assignmentDate > frappe.datetime.str_to_obj(last.date)) {
					last = row;
				}
			}
		}
		return last?.teamlead || null;
	} catch (err) {
		console.warn("[UserTimesheet] getCurrentTeamLead", err);
		return null;
	}
}

/** Resolve frm.ut.isTeamLead for canEdit (owner/SM already covered in model). */
export async function resolveTeamLeadAccess(frm) {
	if (!frm?.ut) {
		return false;
	}
	const user = frappe.session.user;
	if (user === frm.doc.timesheet_from || frappe.user?.has_role?.("System Manager")) {
		frm.ut.isTeamLead = false;
		return false;
	}
	const lead = await getCurrentTeamLead(frm.doc.user_group, frm.doc.ts_valid_from);
	frm.ut.isTeamLead = lead === user;
	return frm.ut.isTeamLead;
}
