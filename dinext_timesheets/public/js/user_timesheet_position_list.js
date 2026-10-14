(function () {
	frappe.provide("dinext_timesheets.approvals");
	const approvals = dinext_timesheets.approvals;
	if (approvals.utpListInstalled) return;
	approvals.utpListInstalled = true;

	const SOURCE_DOCTYPE = "User Timesheet Position";
	const helperAssets = [
		"/assets/dinext_timesheets/js/utp_approval_helpers.js",
		"/assets/dinext_timesheets/css/timesheet_approvals.css",
	];

	const requestId = () =>
		window.crypto?.randomUUID?.() ||
		`${Date.now()}-${Math.random().toString(16).slice(2)}`;

	const getHoursData = async (position) => {
		const response = await frappe.call({
			method: "calculate_timesheet_limits",
			args: { timesheet_name: "", positions: [position] },
			freeze: false,
		});
		const data = response.message?.[0];
		if (!data) return null;
		return {
			totalHours: data.total_hours || 0,
			editingHours: data.hours_data?.Редактирование || 0,
			approvalHours: data.hours_data?.["На согласовании"] || 0,
			approvedHours: data.hours_data?.Согласовано || 0,
			rejectedHours: data.hours_data?.Отклонено || 0,
			plannedHours: data.planned_hours || 0,
		};
	};

	const initializePeriodFilter = (listview) => {
		if (listview.periodFilterInitialized) return;
		const today = () => frappe.datetime.now_date();
		const periods = {
			"Текущая неделя": () => [
				frappe.datetime.week_start(today()),
				frappe.datetime.week_end(today()),
			],
			"Прошлая неделя": () => [
				frappe.datetime.add_days(frappe.datetime.week_start(today()), -7),
				frappe.datetime.add_days(frappe.datetime.week_end(today()), -7),
			],
			"Последние 4 недели": () => [
				frappe.datetime.add_days(today(), -27),
				today(),
			],
			"Текущий месяц": () => [
				frappe.datetime.month_start(today()),
				frappe.datetime.month_end(today()),
			],
			"Прошлый месяц": () => [
				moment().subtract(1, "month").startOf("month").format("YYYY-MM-DD"),
				moment().subtract(1, "month").endOf("month").format("YYYY-MM-DD"),
			],
			"Последние 3 месяца": () => [
				frappe.datetime.add_months(frappe.datetime.month_start(today()), -2),
				frappe.datetime.month_end(today()),
			],
			"Текущий квартал": () => [
				frappe.datetime.quarter_start(today()),
				frappe.datetime.quarter_end(today()),
			],
			"Прошлый квартал": () => [
				frappe.datetime.add_months(frappe.datetime.quarter_start(today()), -3),
				frappe.datetime.add_months(frappe.datetime.quarter_end(today()), -3),
			],
			"Текущий год": () => [
				frappe.datetime.year_start(today()),
				frappe.datetime.year_end(today()),
			],
			"Прошлый год": () => [
				frappe.datetime.add_months(frappe.datetime.year_start(today()), -12),
				frappe.datetime.add_months(frappe.datetime.year_end(today()), -12),
			],
		};
		const control = frappe.ui.form.make_control({
			df: {
				fieldtype: "Select",
				fieldname: "period_filter",
				options: ["", ...Object.keys(periods)].join("\n"),
				onchange() {
					listview.filter_area.remove("date");
					const range = periods[this.get_value()]?.();
					if (range) {
						listview.filter_area.add(
							"User Timesheet Position Details",
							"date",
							"Between",
							range
						);
					}
				},
			},
			parent: listview.filter_area.standard_filters_wrapper,
			render_input: true,
		});
		control.$wrapper.find(".clearfix").hide();
		listview.periodFilterInitialized = true;
	};

	const refreshListLimits = async (positions) => {
		const response = await frappe.call({
			method: "calculate_timesheet_limits",
			args: { timesheet_name: "", positions },
		});
		const styles = {
			block: "#f44336",
			message: "#ff9800",
			warning: "#fbc02d",
			normal: "#4caf50",
			"no-plan": "#9e9e9e",
		};
		(response.message || []).forEach((row) => {
			const button = $(
				`button.plan-fact-button[data-docname="${CSS.escape(
					String(row.position)
				)}"]`
			);
			button.css("color", styles[row.status] || styles["no-plan"]);
			button.attr(
				"title",
				row.planned_hours > 0
					? `${flt(row.completion_percentage).toFixed(1)}% ${__(
							"of"
					  )} ${flt(row.planned_hours).toFixed(1)} ${__("hours")}`
					: __("Planned work efforts are not defined")
			);
		});
	};

	const escape = (value) => frappe.utils.escape_html(String(value ?? ""));

	const showDetails = async (position) => {
		const doc = await frappe.db.get_doc(SOURCE_DOCTYPE, position.name);
		const body = (doc.table || [])
			.map(
				(row) => `<tr>
					<td>${escape(frappe.datetime.str_to_user(row.date))}</td>
					<td>${escape(row.hours)}</td>
					<td>${escape(row.description)}</td>
				</tr>`
			)
			.join("");
		const dialog = new frappe.ui.Dialog({
			title: __("Timesheet details"),
			size: "large",
			primary_action_label: __("Close"),
			primary_action: () => dialog.hide(),
		});
		dialog.$body.html(
			`<div class="table-responsive"><table class="table table-bordered">
				<thead><tr><th>${__("Date")}</th><th>${__("Hours")}</th>
				<th>${__("Description")}</th></tr></thead>
				<tbody>${body || `<tr><td colspan="3">${__("No records")}</td></tr>`}</tbody>
			</table></div>`
		);
		approvals.setModalWindowStyles(dialog);
		dialog.show();
	};

	const showPlanFact = async (position, button) => {
		const hours = await getHoursData(position);
		if (!hours) {
			frappe.msgprint(__("Plan/fact data is unavailable"));
			return;
		}
		const rows = [
			[__("Plan"), hours.plannedHours],
			[__("Total"), hours.totalHours],
			[__("Approved"), hours.approvedHours],
			[__("Pending"), hours.approvalHours],
			[__("Editing"), hours.editingHours],
			[__("Rejected"), hours.rejectedHours],
		];
		const dialog = new frappe.ui.Dialog({
			title: __("Plan/fact analysis"),
			size: "large",
			primary_action_label: __("Close"),
			primary_action: () => dialog.hide(),
		});
		dialog.$body.html(
			`<table class="table table-bordered"><tbody>${rows
				.filter(([, value]) => value !== undefined)
				.map(
					([label, value]) =>
						`<tr><th>${escape(label)}</th><td>${escape(flt(value).toFixed(1))}</td></tr>`
				)
				.join("")}</tbody></table>`
		);
		approvals.setModalWindowStyles(dialog);
		dialog.show();
		button?.blur();
	};

	const commentFor = (transition) =>
		new Promise((resolve) => {
			if (!transition.comment_is_required) {
				resolve("");
				return;
			}
			frappe.prompt(
				{
					fieldname: "comment",
					fieldtype: "Small Text",
					label: __("Comment"),
					reqd: 1,
				},
				(values) => resolve(values.comment),
				__("Comment required for {0}", [__(transition.action)]),
				__("Apply")
			);
		});

	const bulkVote = async (names, transition) => {
		const comment = await commentFor(transition);
		const result = await frappe.xcall(
			"dinext_common.workflow_approval.api.bulk_vote",
			{
				doctype: SOURCE_DOCTYPE,
				names,
				action: transition.action,
				transition_uuid: transition.transition_uuid,
				comment,
				request_id: requestId(),
			}
		);
		const failures = result.failed || [];
		if (failures.length) {
			frappe.msgprint({
				title: __("Some workflow items failed"),
				indicator: "orange",
				as_list: true,
				message: failures.map((row) => `${escape(row.name)}: ${escape(row.error)}`),
			});
		}
		return result;
	};

	const installBulkActions = (listview, tasksBySource) => {
		listview.page.remove_inner_button(__("Apply workflow action"));
		listview.page.add_inner_button(__("Apply workflow action"), () => {
			const selected = listview.get_checked_items().map((row) => row.name);
			const tasks = selected.map((name) => tasksBySource.get(name)).filter(Boolean);
			if (!selected.length || tasks.length !== selected.length) {
				frappe.msgprint(__("Select rows that require your decision"));
				return;
			}
			const common = tasks
				.map((task) => new Set(task.available_transitions.map((row) => row.transition_uuid)))
				.reduce((left, right) => new Set([...left].filter((uuid) => right.has(uuid))));
			const catalog = new Map();
			tasks.forEach((task) => {
				task.available_transitions.forEach((row) => catalog.set(row.transition_uuid, row));
			});
			const choices = [...common].sort().map((uuid) => {
				const row = catalog.get(uuid);
				const sameAction = [...catalog.values()].filter((item) => item.action === row.action);
				const suffix =
					sameAction.length > 1
						? [row.allowed, row.next_state].filter(Boolean).join(" → ")
						: "";
				return {
					uuid,
					label: suffix ? `${__(row.action)} (${suffix})` : __(row.action),
				};
			});
			if (!choices.length) {
				frappe.msgprint(__("The selected rows have no common workflow action"));
				return;
			}
			frappe.prompt(
				{
					fieldname: "action",
					fieldtype: "Select",
					label: __("Action"),
					options: choices.map((row) => row.label).join("\n"),
					reqd: 1,
				},
				async ({ action }) => {
					const chosen = choices.find((row) => row.label === action);
					const transition = catalog.get(chosen.uuid);
					await bulkVote(selected, {
						...transition,
						comment_is_required: tasks.some((task) =>
							task.available_transitions.some(
								(row) =>
									row.transition_uuid === chosen.uuid && row.comment_is_required
							)
						),
					});
					listview.refresh();
				},
				__("Apply workflow action"),
				__("Apply")
			);
		});
	};

	const renderRows = async (listview) => {
		await new Promise((resolve) => frappe.require(helperAssets, resolve));
		approvals.hideColumnsAndSidebar(listview);
		initializePeriodFilter(listview);
		const queue = await frappe
			.xcall("dinext_common.workflow_approval.api.get_my_queue", { limit: 1000 })
			.catch(() => []);
		const tasksBySource = new Map(
			queue
				.filter((task) => task.reference_doctype === SOURCE_DOCTYPE)
				.map((task) => [task.reference_name, task])
		);
		installBulkActions(listview, tasksBySource);
		listview.data.forEach((position) => {
			const row = listview.$frappe_list
				.find(`a[data-name="${frappe.utils.escape_html(position.name)}"]`)
				.closest(".list-row");
			if (!row.length) return;
			row.find(".dinext-utp-actions").remove();
			const actions = $('<div class="dinext-utp-actions"></div>');
			const plan = $(
				`<button type="button" class="btn btn-default btn-xs plan-fact-button"
					data-docname="${escape(position.name)}" aria-label="${escape(
					__("Plan/fact analysis")
				)}"><i class="fa fa-info-circle" aria-hidden="true"></i></button>`
			).on("click", (event) => {
				event.preventDefault();
				event.stopPropagation();
				showPlanFact(position, event.currentTarget);
			});
			const details = $(
				`<button type="button" class="btn btn-default btn-xs" aria-label="${escape(
					__("Timesheet details")
				)}"><i class="fa fa-list" aria-hidden="true"></i></button>`
			).on("click", (event) => {
				event.preventDefault();
				event.stopPropagation();
				showDetails(position);
			});
			actions.append(plan, details);
			approvals.addHistoryButton(actions, position);
			const task = tasksBySource.get(position.name);
			if (task) {
				const select = $(
					`<select class="form-control input-xs dinext-utp-action-select"
						aria-label="${escape(__("Workflow action"))}">
						<option value="">${escape(position.status)}</option>
					</select>`
				);
				task.available_transitions.forEach((transition, index) => {
					const sameAction = task.available_transitions.filter(
						(row) => row.action === transition.action
					);
					const suffix =
						sameAction.length > 1
							? [transition.allowed, transition.next_state].filter(Boolean).join(" → ")
							: "";
					select.append(
						$("<option>")
							.val(String(index))
							.text(
								suffix
									? `${__(transition.action)} (${suffix})`
									: __(transition.action)
							)
					);
				});
				select.on("click", (event) => event.stopPropagation());
				select.on("change", async (event) => {
					event.stopPropagation();
					const transition = task.available_transitions[Number(select.val())];
					select.val("");
					if (!transition) return;
					await bulkVote([position.name], transition);
					listview.refresh();
				});
				actions.append(select);
			}
			const status = $(
				`<span class="indicator-pill ${escape(
					approvals.getSelectStyle(position.status)
				)}">${escape(position.status)}</span>`
			);
			actions.prepend(status);
			row.find(".level-right").prepend(actions);
		});
		await refreshListLimits(listview.data);
	};

	frappe.listview_settings[SOURCE_DOCTYPE] = {
		hide_name_column: true,
		hide_name_filter: true,
		add_fields: [
			"custom_username",
			"document_type",
			"document_name",
			"project",
			"project_role",
			"user_timesheet",
			"status",
			"all_hours",
			"document_subject",
		],
		formatters: {
			all_hours: (value) => frappe.format(value, { fieldtype: "Float" }),
			document_name: (value, _df, doc) => doc.document_subject || value,
			user: (value, _df, doc) => doc.custom_username || value,
		},
		get_form_link: (doc) =>
			frappe.utils.get_form_link("User Timesheet", doc.user_timesheet),
		refresh: renderRows,
	};
})();
