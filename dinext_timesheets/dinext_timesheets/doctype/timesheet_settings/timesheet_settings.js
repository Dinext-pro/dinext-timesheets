(() => {
	const optionsMethod = "dinext_timesheets.timesheet_settings.visible_status_options";
	const workflowDoctypes = ["Workflow", "Workflow State"];
	const namespace = ".dinextTimesheetStatusChoices";

	function isActive(frm) {
		const route = frappe.get_route();
		return window.cur_frm === frm && route[0] === "Form" && route[1] === "Timesheet Settings";
	}

	function clearLinkChoices(grid) {
		for (const row of grid.grid_rows || []) {
			const controls = [
				row.on_grid_fields_dict?.position_status,
				row.grid_form?.fields_dict?.position_status,
			];
			for (const control of controls) {
				if (control?.$input) control.$input.cache = {};
				if (control?.awesomplete) control.awesomplete.list = [];
			}
		}
	}

	function applyChoices(frm, states) {
		const grid = frm.fields_dict.visible_list_statuses.grid;
		const options = states.join("\n");
		if (grid.get_docfield("position_status").options !== options) {
			grid.update_docfield_property("position_status", "options", options);
		}
		clearLinkChoices(frm.fields_dict.position_rules.grid);
	}

	function refreshChoices(frm) {
		const state = frm._dinext_status_choices;
		if (!isActive(frm)) return Promise.resolve();
		state.again = true;
		if (state.pending) return state.pending;
		state.pending = (async () => {
			try {
				while (state.again && isActive(frm)) {
					state.again = false;
					const generation = state.generation;
					const states = await frappe.xcall(optionsMethod);
					if (generation === state.generation && isActive(frm))
						applyChoices(frm, states || []);
				}
			} finally {
				state.pending = null;
			}
		})();
		return state.pending;
	}

	function stop(frm) {
		const state = frm._dinext_status_choices;
		if (!state.bound) return;
		state.bound = false;
		state.again = false;
		state.generation += 1;
		frappe.realtime.off("list_update", state.onUpdate);
		frappe.realtime.off("connect", state.onConnect);
		$(frm.wrapper).off(namespace);
		$(window).off(namespace);
		$(document).off(`visibilitychange${namespace}`);
	}

	function start(frm) {
		const state = frm._dinext_status_choices;
		if (!isActive(frm) || state.bound) return;
		state.bound = true;
		// Rooms are shared with cached native lists; detach only our event listeners on exit.
		workflowDoctypes.forEach((doctype) => frappe.realtime.doctype_subscribe(doctype));
		frappe.realtime.on("list_update", state.onUpdate);
		frappe.realtime.on("connect", state.onConnect);
		$(frm.wrapper).on(
			`focusin${namespace}`,
			'[data-fieldname="position_status"] input, [data-fieldname="position_status"] select',
			state.refresh
		);
		$(window).on(`focus${namespace}`, state.refresh);
		$(document).on(`visibilitychange${namespace}`, () => {
			if (!document.hidden) state.refresh();
		});
	}

	frappe.ui.form.on("Timesheet Settings", {
		setup(frm) {
			frm.set_query("position_status", "position_rules", () => ({
				query: "dinext_timesheets.timesheet_settings.utp_state_query",
			}));
			const state = {
				bound: false,
				again: false,
				pending: null,
				generation: 0,
			};
			frm._dinext_status_choices = state;
			// Frappe already reports RPC errors; later focus/refresh retries the authoritative read.
			state.refresh = () => refreshChoices(frm).catch(() => {});
			state.onUpdate = (data) => {
				if (data && workflowDoctypes.includes(data.doctype)) state.refresh();
			};
			state.onConnect = () => {
				if (!isActive(frm)) return;
				workflowDoctypes.forEach((doctype) => frappe.realtime.doctype_subscribe(doctype));
				state.refresh();
			};
			$(document)
				.off(`page-change${namespace}`)
				.on(`page-change${namespace}`, () => {
					if (isActive(frm)) {
						start(frm);
					} else {
						stop(frm);
					}
				});
		},
		refresh(frm) {
			start(frm);
			return refreshChoices(frm);
		},
	});

	frappe.ui.form.on("Timesheet Hidden List Status", {
		position_status(frm, cdt, cdn) {
			const row = locals[cdt][cdn];
			if (
				frm.doctype === "Timesheet Settings" &&
				row.parentfield === "visible_list_statuses"
			) {
				return frappe.model.set_value(
					cdt,
					cdn,
					"open_wf_task",
					row.position_status === "Pending Approval" ? 1 : 0
				);
			}
		},
	});
})();
