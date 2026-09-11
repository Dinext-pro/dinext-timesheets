/**
 * Form dashboard comments (demodev showDashboard).
 * Approvers / overdue / JE related links.
 */
export async function showTimesheetDashboard(frm) {
	if (!frm?.dashboard?.reset || frm.is_new()) {
		return;
	}
	frm.dashboard.reset();

	if (frm.doc.ut_status === "На согласовании") {
		const positionNames = (frm.ts_positions || []).map((x) => x.name).filter(Boolean);
		if (positionNames.length) {
			const wfTasks = await frappe.db.get_list("Workflow Task", {
				fields: ["name", "_assign"],
				filters: {
					status: "Working",
					state: frm.doc.ut_status,
					doc: "User Timesheet Position",
					wt_docname: ["in", positionNames],
					_assign: ["not like", `%${frm.doc.timesheet_from}%`],
				},
				limit: 100,
			});
			if (wfTasks?.length) {
				const approvers = [
					...new Set(
						wfTasks
							.map((x) => frappe.utils.parse_json(x._assign) || [])
							.flat()
							.filter(Boolean)
					),
				];
				if (approvers.length) {
					const users = await frappe.db.get_list("User", {
						fields: ["full_name"],
						filters: { name: ["in", approvers] },
						limit: approvers.length,
					});
					const names = (users || []).map((u) => u.full_name).filter(Boolean);
					if (names.length) {
						frm.dashboard.add_comment(
							__("Ожидается согласование от: {0}", [
								frappe.utils.comma_and(names),
							]),
							"blue",
							true
						);
					}
				}
			}
		}
	}

	if (
		frm.doc.is_overdue &&
		(frm.doc.ut_status === "Черновик" || frm.doc.ut_status === "На доработке")
	) {
		frm.dashboard.add_comment(
			__("Таймшит просрочен! Срочно отправьте позиции на согласование!"),
			"orange",
			true
		);
	}

	if (frm.doc.ut_status === "Согласован") {
		frm.dashboard.add_transactions({
			label: __("Related Documents"),
			items: ["Journal Entry"],
		});
		frm.dashboard.refresh?.();
	}
}
