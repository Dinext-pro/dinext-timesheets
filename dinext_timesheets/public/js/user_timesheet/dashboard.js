/**
 * Form dashboard comments (V10 showDashboard).
 * Approvers / overdue / JE Connections.
 *
 * No dashboard.reset() here: it hides Connections and races refresh.
 * add_comment appends headlines — clear first, apply once.
 * JE link lives on DocType (`custom_user_timesheet`). Do not add_transactions
 * or refresh(): both duplicate the badge; refresh() also reset()s.
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

	applyJournalEntryConnections(frm);
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
