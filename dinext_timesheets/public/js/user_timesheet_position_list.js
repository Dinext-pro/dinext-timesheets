(function () {
	if (!frappe.boot?.enable_parallel_workflow_approval) return;
	frappe.provide("dinext_timesheets.approvals");
	const approvals = dinext_timesheets.approvals;
	if (approvals.utpListInstalled) return;
	approvals.utpListInstalled = true;

	const SOURCE_DOCTYPE = "User Timesheet Position";
	const TIMESHEET_LIMITS_METHOD =
		"project_workload_assignment.api.calculate_user_timesheet_limits";
	const helperAssets = [
		"/assets/dinext_timesheets/js/utp_approval_helpers.js",
		"/assets/dinext_timesheets/css/timesheet_approvals.css",
	];

	const requestId = () =>
		window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;

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
			"Последние 4 недели": () => [frappe.datetime.add_days(today(), -27), today()],
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
		if (!positions.length) return;
		const response = await frappe.call({
			method: TIMESHEET_LIMITS_METHOD,
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
				`button.plan-fact-button[data-docname="${CSS.escape(String(row.position))}"]`
			);
			button.css("color", styles[row.status] || styles["no-plan"]);
			button.attr(
				"title",
				row.planned_hours > 0
					? `${flt(row.completion_percentage).toFixed(1)}% ${__("of")} ${flt(
							row.planned_hours
					  ).toFixed(1)} ${__("hours")}`
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
		const response = await frappe.call({
			method: TIMESHEET_LIMITS_METHOD,
			args: { timesheet_name: "", positions: [position] },
			freeze: false,
		});
		await frappe.require("/assets/project_workload_assignment/js/limits/plan_fact.js");
		const dialog = await project_workload_assignment.plan_fact_details.show({
			results: response.message || [],
			title: position.document_subject || position.document_name,
			ownerName: position.custom_username,
		});
		button?.blur();
		return dialog;
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
		const result = await frappe.xcall("dinext_common.workflow_approval.api.bulk_vote", {
			doctype: SOURCE_DOCTYPE,
			names,
			action: transition.action,
			transition_uuid: transition.transition_uuid,
			comment,
			request_id: requestId(),
		});
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

	const loadDocumentSubjects = async (listview) => {
		const column = listview.columns?.findIndex(
			(item) => item.df?.fieldname === "document_name"
		);
		if (column == null || column < 0) return;
		const positions = [...listview.data];
		await Promise.all(
			["Task", "Issue"].map(async (doctype) => {
				if (!frappe.model.can_read(doctype)) return;
				const matching = positions.filter(
					(row) => row.document_type === doctype && row.document_name
				);
				const names = [...new Set(matching.map((row) => row.document_name))];
				if (!names.length) return;
				const records = await frappe.db
					.get_list(doctype, {
						fields: ["name", "subject"],
						filters: { name: ["in", names] },
						limit: names.length,
					})
					.catch(() => []);
				const subjects = new Map(records.map((row) => [row.name, row.subject]));
				for (const position of matching) {
					const subject = subjects.get(position.document_name);
					if (!subject || !listview.data.includes(position)) continue;
					position.document_subject = subject;
					listview.$frappe_list
						.find(`a[data-name="${CSS.escape(position.name)}"]`)
						.closest(".list-row")
						.children(".level-left")
						.children(".list-row-col")
						.eq(column)
						.text(subject)
						.attr("title", subject);
				}
			})
		);
	};

	const renderRows = async (listview) => {
		listview.$frappe_list.addClass("dinext-utp-list");
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
			if (task?.available_transitions?.length) {
				const select = $(
					`<select class="form-control input-xs dinext-utp-action-select ${escape(
						approvals.getSelectStyle(position.status)
					)}"
						aria-label="${escape(__("Workflow action"))}">
						<option value="">${escape(__(position.status))}</option>
					</select>`
				);
				task.available_transitions.forEach((transition, index) => {
					const sameAction = task.available_transitions.filter(
						(row) => row.action === transition.action
					);
					const suffix =
						sameAction.length > 1
							? [transition.allowed, transition.next_state]
									.filter(Boolean)
									.join(" → ")
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
				actions.prepend(select);
			} else {
				const status = $(
					`<span class="indicator-pill ${escape(
						approvals.getSelectStyle(position.status)
					)}">${escape(__(position.status))}</span>`
				);
				actions.prepend(status);
			}
			row.find(".level-right").prepend(actions);
		});
		await Promise.all([refreshListLimits(listview.data), loadDocumentSubjects(listview)]);
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
			all_hours: (value) => frappe.format(value, { fieldtype: "Data" }),
			document_name: (value, _df, doc) => escape(doc.document_subject || value),
			user: (value, _df, doc) => doc.custom_username || value,
		},
		get_form_link: (doc) => frappe.utils.get_form_link("User Timesheet", doc.user_timesheet),
		refresh: renderRows,
	};
})();
