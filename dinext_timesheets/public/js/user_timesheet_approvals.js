(function () {
	frappe.provide("dinext_timesheets.approvals");
	const approvals = dinext_timesheets.approvals;
	if (approvals.timesheetApprovalsInstalled) return;
	approvals.timesheetApprovalsInstalled = true;

	const requestId = () =>
		window.crypto?.randomUUID?.() ||
		`${Date.now()}-${Math.random().toString(16).slice(2)}`;

	const positionPayload = (position) => ({
		name: position.name,
		new: position.new || position.__islocal || /^\d+$/.test(String(position.name || "")),
		project: position.project,
		document_type: position.document_type,
		document_name: position.document_name,
		project_role: position.project_role,
		table: (position.table || position.details || []).map((row) => ({
			date: row.date,
			hours: flt(row.hours),
			description: String(row.description || "").trim(),
		})),
	});

	const limitPayload = (frm) => {
		const deleted = new Set(frm.deletedPositions || []);
		return {
			timesheet_name: frm.doc.name,
			positions: (frm.ts_positions || [])
				.filter((position) => !deleted.has(position.name))
				.map((position) => ({
					...positionPayload(position),
					status: position.status,
					all_hours: (position.table || position.details || []).reduce(
						(total, row) => total + flt(row.hours),
						0
					),
				})),
		};
	};

	approvals.getTimesheetLimits = async function (frm) {
		if (!frm.doc.name || !Array.isArray(frm.ts_positions)) return [];
		const response = await frappe.call({
			method: "calculate_timesheet_limits",
			args: limitPayload(frm),
		});
		return response.message || [];
	};

	approvals.checkLimits = async function (frm) {
		const rows = await approvals.getTimesheetLimits(frm);
		return rows.filter((row) => ["block", "warning"].includes(row.status));
	};

	approvals.refreshLimits = async function (frm) {
		const styles = {
			block: { color: "#f44336" },
			message: { color: "#ff9800" },
			warning: { color: "#fbc02d" },
			normal: { color: "#4caf50" },
			"no-plan": { color: "#9e9e9e" },
		};
		const rows = await approvals.getTimesheetLimits(frm);
		rows.forEach((row) => {
			const button = $(`#limits-${CSS.escape(String(row.position))}`);
			if (!button.length) return;
			button.css(styles[row.status] || styles["no-plan"]);
			button.attr(
				"title",
				row.planned_hours > 0
					? `${flt(row.completion_percentage).toFixed(1)}% ${__(
							"of"
					  )} ${flt(row.planned_hours).toFixed(1)} ${__("hours")}`
					: __("Planned work efforts are not defined")
			);
		});
		return rows;
	};

	approvals.checkPlannedHoursAndLimits = async function (frm) {
		const errors = [];
		const warnings = [];
		try {
			const rows = await approvals.getTimesheetLimits(frm);
			rows.forEach((row) => {
				if (row.status === "block") {
					if (flt(row.planned_hours) > 0) {
						const maximum = (flt(row.limit) * flt(row.planned_hours)) / 100;
						errors.push(
							__(
								'Task "{0}" (role: {1}) exceeds the blocking limit by {2} hours',
								[
									row.task_subject,
									row.role,
									(flt(row.total_hours) - maximum).toFixed(1),
								]
							)
						);
					} else {
						errors.push(
							__('Task "{0}" (role: {1}) has no required planned hours', [
								row.task_subject,
								row.role,
							])
						);
					}
				} else if (row.status === "warning") {
					warnings.push(row);
				}
			});
		} catch (error) {
			console.error("Unable to check planned timesheet limits", error);
			errors.push(__("Unable to check planned work efforts and limits"));
		}
		return { errors, warnings, hasCriticalErrors: errors.length > 0 };
	};

	approvals.showTaskPlanFact = async function (position, frm, button) {
		if (!position.document_name) {
			frappe.msgprint(__("Select a task or issue first"));
			return;
		}
		const rows = await approvals.getTimesheetLimits(frm);
		const result = rows.find((row) => row.position === position.name);
		if (!result) {
			frappe.msgprint(__("Plan/fact data is unavailable"));
			return;
		}
		const hours = result.hours_data || {};
		const body = Object.entries(hours)
			.filter(([status]) => status !== "users")
			.map(
				([status, value]) => `<tr>
					<td>${frappe.utils.escape_html(status === "total" ? __("Total") : status)}</td>
					<td class="text-right">${frappe.utils.escape_html(
						flt(result.planned_hours).toFixed(1)
					)}</td>
					<td class="text-right">${frappe.utils.escape_html(flt(value).toFixed(1))}</td>
				</tr>`
			)
			.join("");
		const dialog = new frappe.ui.Dialog({
			title: result.task_subject || position.document_name,
			size: "large",
			primary_action_label: __("Close"),
			primary_action: () => dialog.hide(),
		});
		dialog.$body.html(
			`${result.plan_required && flt(result.planned_hours) <= 0
				? `<div class="alert alert-danger">${__(
						"Required planned work efforts are not defined"
				  )}</div>`
				: ""}
			<table class="table table-bordered">
				<thead><tr><th>${__("Status")}</th><th>${__("Plan")}</th><th>${__(
					"Actual"
				)}</th></tr></thead>
				<tbody>${body}</tbody>
			</table>
			<p class="text-muted">${__("Planned data level")}: ${frappe.utils.escape_html(
				result.plan_task_subject || result.task_subject || position.document_name
			)}</p>`
		);
		dialog.show();
		button?.blur();
	};

	approvals.disableCopyPosition = function (frm) {
		if (!["На доработке", "Черновик"].includes(frm.doc.ut_status)) {
			const group = frappe.utils.icon("sidebar-expand") + __("Copy");
			frm.remove_custom_button(__("Positions from Previous Timesheet"), group);
			frm.remove_custom_button(__("Data from Planned Workload"), group);
		}
	};

	const positionSignature = (position) =>
		[
			position?.document_type,
			position?.document_name,
			position?.user,
			position?.project,
			position?.project_role,
		]
			.map((value) => value || "")
			.join("::");

	const copyPositions = async (frm, method, validTasks, renderPositions) => {
		approvals.disableCopyPosition(frm);
		const response = await frappe.call({
			method,
			args: { doc: frm.doc, valid_tasks: validTasks || [] },
			freeze: true,
			silent: true,
		});
		const result = response?.message;
		if (!result?.success || !Array.isArray(result.data?.positions)) {
			frappe.throw(result?.message || __("Invalid server response format"));
		}
		const deleted = new Set(frm.deletedPositions || []);
		const existing = new Set(
			(frm.ts_positions || [])
				.filter((position) => !deleted.has(position.name))
				.map(positionSignature)
		);
		const copied = [];
		let localDuplicates = 0;
		result.data.positions.forEach((position) => {
			const signature = positionSignature(position);
			if (existing.has(signature)) {
				localDuplicates += 1;
				return;
			}
			existing.add(signature);
			copied.push({ ...position, new: true });
		});
		renderPositions(copied);
		const duplicateCount = flt(result.data.duplicates_count) + localDuplicates;
		frappe.show_alert(
			{
				message: __("{0} copied; {1} duplicate(s) skipped", [
					copied.length,
					duplicateCount,
				]),
				indicator: copied.length ? "green" : "orange",
			},
			8
		);
	};

	approvals.addCopyPositionsButton = function (
		frm,
		customers,
		fullDates,
		filteredHolidays,
		renderPositions
	) {
		const group = frappe.utils.icon("sidebar-expand") + __("Copy");
		frm.add_custom_button(
			__("Positions from Previous Timesheet"),
			() =>
				copyPositions(
					frm,
					"copy_positions_from_previous_timesheet",
					[],
					renderPositions
				),
			group
		);
		frm.add_custom_button(
			__("Data from Planned Workload"),
			() => {
				const validTasks = (frm.tasks_data || []).flatMap((customer) =>
					Object.values(customer).flatMap((projects) =>
						projects.flatMap((project) =>
							(project.tasks_issues || [])
								.filter((row) => row.tsdoctype === "Task" && row.name)
								.map((row) => row.name)
						)
					)
				);
				return copyPositions(
					frm,
					"copy_positions_from_project_workload_assignment",
					validTasks,
					renderPositions
				);
			},
			group
		);
	};

	approvals.orchestrateTimesheet = async function (
		frm,
		operation,
		positions = null,
		deletedPositions = null
	) {
		const payload = (positions || frm.ts_positions || []).map(positionPayload);
		const result = await frappe.xcall(
			"dinext_timesheets.workflow_approval.orchestrate_timesheet",
			{
				ts_name: frm.doc.name,
				operation,
				positions: payload,
				deleted_positions: deletedPositions || frm.deletedPositions || [],
			}
		);
		return result;
	};

	approvals.refreshPendingApprovers = async function (frm) {
		if (frm.is_new() || !Array.isArray(frm.ts_positions)) return;
		const selector = ".dinext-pending-approvers";
		frm.dashboard.wrapper.find(selector).remove();
		const rows = await frappe
			.xcall("dinext_common.workflow_approval.api.get_pending_approvers", {
				doctype: frm.doctype,
				name: frm.doc.name,
			})
			.catch(() => []);
		if (!rows.length) return;
		const grouped = new Map();
		rows.forEach((row) => {
			const key = row.approver;
			const entry = grouped.get(key) || {
				name: row.approver_name || row.approver,
				positions: [],
			};
			if (row.reference_name && !entry.positions.includes(row.reference_name)) {
				entry.positions.push(row.reference_name);
			}
			grouped.set(key, entry);
		});
		const content = [...grouped.values()]
			.sort((left, right) => left.name.localeCompare(right.name))
			.map((entry) => {
				const links = entry.positions
					.sort()
					.map(
						(name) =>
							`<a href="${frappe.utils.get_form_link(
								"User Timesheet Position",
								name
							)}">${frappe.utils.escape_html(name)}</a>`
					)
					.join(", ");
				return `<div class="dinext-approver-row">
					<span>${frappe.utils.escape_html(entry.name)}</span>
					<span class="text-muted">${__(
						"{0} position(s)",
						[entry.positions.length]
					)}${links ? `: ${links}` : ""}</span>
				</div>`;
			})
			.join("");
		frm.dashboard.wrapper.prepend(
			`<div class="form-dashboard-section dinext-pending-approvers">
				<div class="section-head">${__("Pending approvers")}</div>
				<div class="section-body">${content}</div>
			</div>`
		);
	};

	const applyTimesheetAction = (frm, transition) => {
		const submit = async (comment = "") => {
			await frappe.xcall(
				"dinext_timesheets.workflow_approval.vote_timesheet_positions",
				{
					timesheet_name: frm.doc.name,
					action: transition.action,
					comment,
					request_id: requestId(),
				}
			);
			frappe.show_alert({
				message: __("Workflow action recorded"),
				indicator: "green",
			});
			await frm.reload_doc();
		};
		if (!transition.comment_is_required) return submit();
		frappe.prompt(
			[
				{
					fieldname: "comment",
					fieldtype: "Small Text",
					label: __("Comment"),
					reqd: 1,
				},
			],
			(values) => submit(values.comment),
			__("Comment required for {0}", [__(transition.action)]),
			__("Apply")
		);
	};

	frappe.ui.form.on("User Timesheet", {
		async refresh(frm) {
			frappe.require([
				"/assets/dinext_timesheets/css/timesheet_approvals.css",
			]);
			if (
				!frappe.boot?.enable_parallel_workflow_approval ||
				frm.is_new()
			)
				return;
			const response = await frappe
				.xcall(
					"dinext_timesheets.workflow_approval.get_timesheet_approval_actions",
					{ timesheet_name: frm.doc.name }
				)
				.catch(() => null);
			(response?.actions || []).forEach((transition) => {
				frm.add_custom_button(
					__(transition.action),
					() => applyTimesheetAction(frm, transition),
					__("Workflow")
				);
			});
			await approvals.refreshPendingApprovers(frm);
		},
	});
})();
