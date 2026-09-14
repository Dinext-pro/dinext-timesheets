/**
 * Form dashboard comments (demodev showDashboard).
 * Approvers / overdue / JE related links.
 *
 * Do not call dashboard.reset(): it hides Connections (links_area).
 * add_comment appends headlines — clear first, apply once, drop stale races.
 */
export async function showTimesheetDashboard(frm) {
	if (!frm?.dashboard || frm.is_new()) {
		return;
	}

	const gen = (frm._ut_dash_gen = (frm._ut_dash_gen || 0) + 1);
	const comments = [];

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
			if (gen !== frm._ut_dash_gen) {
				return;
			}
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
					if (gen !== frm._ut_dash_gen) {
						return;
					}
					const names = (users || []).map((u) => u.full_name).filter(Boolean);
					if (names.length) {
						comments.push({
							text: __("Ожидается согласование от: {0}", [
								frappe.utils.comma_and(names),
							]),
							color: "blue",
						});
					}
				}
			}
		}
	}

	if (
		frm.doc.is_overdue &&
		(frm.doc.ut_status === "Черновик" || frm.doc.ut_status === "На доработке")
	) {
		comments.push({
			text: __("Таймшит просрочен! Срочно отправьте позиции на согласование!"),
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

	if (frm.doc.ut_status === "Согласован") {
		frm.dashboard.add_transactions({
			label: __("Related Documents"),
			items: ["Journal Entry"],
		});
		frm.dashboard.refresh?.();
	}
}
