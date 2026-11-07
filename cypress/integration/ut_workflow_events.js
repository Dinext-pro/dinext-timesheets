Cypress.removeAllListeners("uncaught:exception");

const helper = "dinext_timesheets.tests.ui_test_helpers";
const actionsMethod = "dinext_timesheets.workflow_approval.get_timesheet_position_actions";
const applyMethod = "dinext_timesheets.workflow_approval.apply_timesheet_position_action";
let fixture;

function workflowGroup(win) {
	return win.$(`.inner-group-button[data-label="${encodeURIComponent(win.__("Workflow"))}"]`);
}

function cleanTimesheet() {
	cy.login();
	cy.openDesk("/app");
	cy.call(`${helper}.cleanup_ut_workflow_stop`);
}

function openTimesheet(positionCount = 1) {
	cy.login();
	cy.openDesk("/app");
	cy.call(`${helper}.seed_ut_workflow_stop`, { position_count: positionCount }).then((res) => {
		fixture = res.body.message;
		cy.login(fixture.user, fixture.password);
		cy.openDesk(`/app/user-timesheet/${encodeURIComponent(fixture.name)}`);
		cy.window().should((win) => {
			expect(win.cur_frm?.doc?.name).to.eq(fixture.name);
			expect(workflowGroup(win).length).to.eq(1);
			expect(!!win.cur_frm?._ut_load_promise, "initial form load completed").to.eq(false);
		});
	});
}

context("User Timesheet workflow event refresh", () => {
	after(cleanTimesheet);
	beforeEach(() => openTimesheet());

	it("restores the editing Workflow menu after stopping without a browser reload", () => {
		let releaseDashboard;
		let dashboardPending = false;
		let holdNext = true;
		const gate = new Promise((resolve) => {
			releaseDashboard = resolve;
		});
		cy.intercept("POST", `**/api/method/${applyMethod}`).as("applyAction");
		cy.window().then((win) => {
			win.__workflowPageMarker = "same-page";
			cy.spy(win.frappe, "show_alert").as("alert");
			cy.spy(win.frappe, "show_progress").as("singlePositionProgress");
			const original = win.UserTimesheet.showTimesheetDashboard;
			win.UserTimesheet.showTimesheetDashboard = async (frm) => {
				await original(frm);
				if (holdNext) {
					holdNext = false;
					dashboardPending = true;
					await gate;
				}
			};
			workflowGroup(win).find("button").first().click();
		});
		cy.window().then((win) => {
			cy.get(".inner-group-button .dropdown-menu a").contains(win.__(fixture.stop_action)).click();
		});
		cy.wait("@applyAction").its("response.statusCode").should("eq", 200);
		cy.wrap(null).should(() =>
			expect(dashboardPending, "refresh reached dashboard").to.eq(true)
		);
		cy.window().then((win) => {
			expect(win.cur_frm.page.wrapper[0].inert, "form locked through refresh").to.eq(true);
			// Repeat Frappe's control-clear and refresh dispatch while the first pass is pending.
			win.cur_frm.clear_custom_buttons();
			const next = win.cur_frm.script_manager.trigger("refresh");
			queueMicrotask(releaseDashboard);
			return next;
		});
		cy.call(actionsMethod, { timesheet_name: fixture.name }).then((res) => {
			expect(res.body.message.actions.map((row) => row.action)).to.include.members(
				fixture.editing_actions
			);
		});
		cy.window().should((win) => {
			expect(win.__workflowPageMarker).to.eq("same-page");
			expect(win.cur_frm.page.wrapper[0].inert, "form unlocked after refresh").to.eq(false);
			const group = workflowGroup(win);
			expect(group.length, "Workflow menu restored").to.eq(1);
			for (const action of fixture.editing_actions) expect(group.text()).to.contain(win.__(action));
		});
		cy.get("@alert").should("not.have.been.called");
		cy.get("@singlePositionProgress").should("not.have.been.called");
	});

	it("shows one parent activity entry for each new position workflow event", () => {
		let events;
		let copies;
		cy.call(applyMethod, {
			timesheet_name: fixture.name,
			action: fixture.stop_action,
			request_id: `cypress-workflow-event-${Date.now()}`,
		});
		cy.call("frappe.desk.form.load.getdoc", {
			doctype: "User Timesheet Position",
			name: fixture.position,
		}).then((res) => {
			events = res.body.docinfo.workflow_logs;
			expect(events.length).to.be.greaterThan(0);
		});
		cy.call("frappe.desk.form.load.getdoc", {
			doctype: "User Timesheet",
			name: fixture.name,
		}).then((res) => {
			copies = res.body.docinfo.workflow_logs.filter(
				(row) =>
					row.comment_type === "Workflow" &&
					row.content.startsWith(`${fixture.position}:`)
			);
			expect(copies).to.have.length(events.length);
			for (const event of events) {
				const text = `${fixture.position}: ${event.content}`;
				expect(copies.filter((row) => row.content === text)).to.have.length(
					events.filter((row) => row.content === event.content).length
				);
			}
		});
		cy.window().then((win) => win.cur_frm.reload_doc());
		cy.get(".timeline-content").should(($items) => {
			for (const content of new Set(copies.map((row) => row.content))) {
				const text = Cypress.$("<div>").html(content).text();
				const matches = $items.filter((_, item) => item.textContent.includes(text));
				expect(matches.length, "one activity item per source event").to.eq(
					copies.filter((row) => row.content === content).length
				);
			}
		});
	});
});

context("User Timesheet progress for two positions", () => {
	after(cleanTimesheet);
	beforeEach(() => openTimesheet(2));

	it("keeps progress visible until the parent action returns and the form refreshes", () => {
		let releaseResponse;
		let releaseRefresh;
		const responseGate = new Promise((resolve) => {
			releaseResponse = resolve;
		});
		const refreshGate = new Promise((resolve) => {
			releaseRefresh = resolve;
		});
		cy.intercept({
			method: "GET",
			pathname: "/api/method/frappe.desk.form.load.getdoc",
			query: { doctype: "User Timesheet", name: fixture.name },
		}, (req) => {
			req.continue(() => refreshGate);
		}).as("refreshTimesheet");
		cy.intercept("POST", `**/api/method/${applyMethod}`, (req) => {
			req.continue(() => responseGate);
		}).as("applyPositions");
		cy.window().then((win) => {
			cy.spy(win.frappe, "show_progress").as("positionProgress");
			workflowGroup(win).find("button").first().click();
			cy.get(".inner-group-button .dropdown-menu a").contains(win.__(fixture.stop_action)).click();
		});
		cy.get(".modal:visible .progress").should("be.visible");
		cy.contains(".modal:visible .modal-title", "Обработка:").should("be.visible");
		cy.window().should((win) => {
			expect(win.cur_frm.page.wrapper[0].inert).to.eq(true);
		});
		cy.get("@positionProgress").should("have.been.calledWith", Cypress.sinon.match.string, 0, 2);
		cy.then(releaseResponse);
		cy.wait("@applyPositions").then(({ request, response }) => {
			const args = typeof request.body === "string"
				? Object.fromEntries(new URLSearchParams(request.body))
				: request.body;
			expect(String(args.track_progress)).to.eq("true");
			expect(args.request_id).to.be.a("string").and.not.be.empty;
			expect(response.statusCode).to.eq(200);
			const result = response.body.message;
			expect(result.processed).to.eq(2);
			expect(result.total).to.eq(2);
			expect(result.results.map((row) => row.name)).to.have.members(fixture.positions);
		});
		cy.get("@positionProgress").should("have.been.calledWith", Cypress.sinon.match.string, 2, 2);
		cy.get(".modal:visible .progress").should("be.visible");
		cy.window().should((win) => {
			expect(win.cur_frm.page.wrapper[0].inert).to.eq(true);
		});
		cy.then(releaseRefresh);
		cy.wait("@refreshTimesheet").its("response.statusCode").should("eq", 200);
		cy.get(".modal:visible .progress").should("not.exist");
		cy.get(".modal:visible").should("not.exist");
		cy.get("#freeze, .modal-backdrop").should("not.exist");
		cy.window().should((win) => {
			expect(win.cur_frm.page.wrapper[0].inert).to.eq(false);
			const group = workflowGroup(win);
			for (const action of fixture.editing_actions) expect(group.text()).to.contain(win.__(action));
		});
		cy.window().then((win) => {
			cy.wrap(workflowGroup(win).find("button").first()).click();
		});
		cy.get(".inner-group-button .dropdown-menu:visible").should("exist");
	});

	it("restores interaction when refreshing after a completed batch fails", () => {
		cy.intercept({
			method: "GET",
			pathname: "/api/method/frappe.desk.form.load.getdoc",
			query: { doctype: "User Timesheet", name: fixture.name },
		}, { body: {} }).as("failedRefresh");
		cy.window().then((win) => {
			workflowGroup(win).find("button").first().click();
			cy.get(".inner-group-button .dropdown-menu a").contains(win.__(fixture.stop_action)).click();
		});
		cy.wait("@failedRefresh");
		cy.window().should((win) => {
			expect(win.cur_frm.page.wrapper[0].inert).to.eq(false);
			expect(win.frappe.dom.freeze_count).to.eq(0);
			expect(win.frappe.cur_progress == null).to.eq(true);
		});
		cy.window().then((win) => {
			cy.contains(".modal:visible", win.__("Could not reload the workflow document")).should("be.visible");
		});
		cy.window().should((win) => expect(win.cur_dialog?.display).to.eq(true));
		cy.get(".modal:visible .modal-header button.btn-modal-close").click();
		cy.get("#freeze, .modal-backdrop").should("not.exist");
	});
});
