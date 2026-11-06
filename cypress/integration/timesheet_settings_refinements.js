Cypress.removeAllListeners("uncaught:exception");
const httpErrors = [];
Cypress.on("fail", (error) => {
	if (httpErrors.length)
		error.message += "\nSafe HTTP diagnostics: " + JSON.stringify(httpErrors);
	throw error;
});
beforeEach(() => {
	cy.intercept("**/api/**", (req) => {
		req.on("response", (res) => {
			if (res.statusCode >= 400)
				httpErrors.push({
					url: req.url.split("?")[0],
					status: res.statusCode,
					exception: String(res.body?.exception || "").slice(0, 500),
				});
		});
	});
});

const helper = "dinext_timesheets.tests.timesheet_settings_ui";
let fixture;

function openSettings() {
	cy.login();
	cy.openDesk("/app/timesheet-settings/Timesheet%20Settings");
	cy.window({ timeout: 60000 }).should((win) => {
		expect(win.cur_frm?.doctype).to.eq("Timesheet Settings");
		expect(win.cur_frm?.fields_dict.visible_list_statuses?.grid).to.exist;
	});
}

context("Current timesheet status settings", { defaultCommandTimeout: 15000 }, () => {
	before(() => {
		openSettings();
		cy.call(`${helper}.seed_settings_refinements`, {}).then((res) => {
			fixture = res.body.message;
		});
	});
	after(() => {
		cy.login();
		cy.openDesk("/app");
		cy.call(`${helper}.cleanup_settings_refinements`, {});
	});

	it("defaults Pending Approval to an open task and preserves an explicit opt-out on reopening", () => {
		openSettings();
		let rowName;
		cy.window().then(async (win) => {
			const frm = win.cur_frm;
			await frm.set_value("visible_list_statuses", []);
			const row = frm.add_child("visible_list_statuses", {});
			rowName = row.name;
			frm.refresh_field("visible_list_statuses");
			await win.frappe.model.set_value(
				row.doctype,
				row.name,
				"position_status",
				"Pending Approval"
			);
		});
		cy.window().should((win) =>
			expect(win.locals["Timesheet Hidden List Status"][rowName].open_wf_task).to.eq(1)
		);
		cy.window().then((win) => {
			const grid = win.cur_frm.fields_dict.visible_list_statuses;
			const cell = `.grid-row[data-name="${rowName}"] [data-fieldname="open_wf_task"]`;
			// Frappe's static Check formatter draws its tick via disabled-selected CSS.
			cy.wrap(grid.wrapper)
				.find(`${cell} .static-area input[type="checkbox"]`)
				.should("have.class", "disabled-selected");
			cy.wrap(grid.wrapper).find(cell).click();
			cy.wrap(grid.wrapper)
				.find(`${cell} .field-area input[type="checkbox"]`)
				.should("be.visible")
				.and("be.checked");
			cy.screenshot("settings-pending-open-task-default", { capture: "viewport" });
			cy.wrap(grid.wrapper).find(`${cell} .field-area input[type="checkbox"]`).uncheck();
		});
		cy.window().then((win) => {
			expect(win.locals["Timesheet Hidden List Status"][rowName].open_wf_task).to.eq(0);
			return win.cur_frm.save();
		});
		openSettings();
		cy.window().should((win) => {
			expect(win.cur_frm.doc.visible_list_statuses).to.have.length(1);
			expect(win.cur_frm.doc.visible_list_statuses[0].open_wf_task).to.eq(0);
		});
		cy.window().then(async (win) => {
			const row = win.cur_frm.doc.visible_list_statuses[0];
			await win.frappe.model.set_value(row.doctype, row.name, "open_wf_task", 1);
			await win.frappe.model.set_value(row.doctype, row.name, "position_status", "Approved");
		});
		cy.window().should((win) =>
			expect(win.cur_frm.doc.visible_list_statuses[0].open_wf_task).to.eq(0)
		);
	});

	it("refetches live status choices on Workflow save without replacing unsaved row values", () => {
		let requests = 0;
		let received;
		cy.intercept(
			"**/api/method/dinext_timesheets.timesheet_settings.visible_status_options",
			(req) => {
				req.on("response", (res) => {
					requests += 1;
					received = res.body.message;
				});
			}
		);
		openSettings();
		cy.window().should(() => expect(requests).to.be.greaterThan(0));
		let before;
		let configured;
		cy.window().then(async (win) => {
			const row = win.cur_frm.doc.visible_list_statuses[0];
			if (row)
				await win.frappe.model.set_value(
					row.doctype,
					row.name,
					"open_wf_task",
					row.open_wf_task ? 0 : 1
				);
			configured = JSON.stringify(
				win.cur_frm.doc.visible_list_statuses.map((r) => ({
					status: r.position_status,
					task: r.open_wf_task,
				}))
			);
			before = requests;
		});
		cy.call(`${helper}.save_owned_workflow`, {});
		cy.window().should(() =>
			expect(requests, "fresh choices after real Workflow save").to.be.greaterThan(before)
		);
		cy.window().should((win) => {
			const frm = win.cur_frm;
			expect(
				JSON.stringify(
					frm.doc.visible_list_statuses.map((r) => ({
						status: r.position_status,
						task: r.open_wf_task,
					}))
				)
			).to.eq(configured);
			expect(received).to.include("Pending Approval");
			expect(received).not.to.include(fixture.inactive_state);
			const options = frm.fields_dict.visible_list_statuses.grid
				.get_docfield("position_status")
				.options.split("\n")
				.filter(Boolean);
			expect(options).to.deep.eq(received);
		});
		cy.call("dinext_timesheets.timesheet_settings.utp_state_query", {
			doctype: "Workflow State",
			txt: "",
			searchfield: "name",
			start: 0,
			page_len: 100,
			filters: {},
		}).then((res) => {
			expect(res.body.message.map((r) => r[0])).to.have.members(
				received.filter((s) => s !== "Not Set")
			);
		});
	});
});
