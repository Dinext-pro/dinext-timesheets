Cypress.removeAllListeners("uncaught:exception");

const helper = "dinext_timesheets.tests.ui_test_helpers";
const actionsMethod = "dinext_timesheets.workflow_approval.get_timesheet_position_actions";
const applyMethod = "dinext_timesheets.workflow_approval.apply_timesheet_position_action";
let fixture;

function workflowGroup(win) {
	return win.$(`.inner-group-button[data-label="${encodeURIComponent(win.__("Workflow"))}"]`);
}

context("User Timesheet workflow event refresh", () => {
	after(() => {
		cy.login();
		cy.openDesk("/app");
		cy.call(`${helper}.cleanup_ut_workflow_stop`);
	});
	beforeEach(() => {
		cy.login();
		cy.openDesk("/app");
		cy.call(`${helper}.seed_ut_workflow_stop`).then((res) => {
			fixture = res.body.message;
		});
	});
	beforeEach(() => {
		cy.login(fixture.user, fixture.password);
		cy.openDesk(`/app/user-timesheet/${encodeURIComponent(fixture.name)}`);
		cy.window().should((win) => {
			expect(win.cur_frm?.doc?.name).to.eq(fixture.name);
			expect(workflowGroup(win).length).to.eq(1);
			expect(!!win.cur_frm?._ut_load_promise, "initial form load completed").to.eq(false);
		});
	});

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
		cy.get(".inner-group-button .dropdown-menu a").contains(fixture.stop_action).click();
		cy.wait("@applyAction").its("response.statusCode").should("eq", 200);
		cy.wrap(null).should(() =>
			expect(dashboardPending, "refresh reached dashboard").to.eq(true)
		);
		cy.window().then((win) => {
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
			const group = workflowGroup(win);
			expect(group.length, "Workflow menu restored").to.eq(1);
			for (const action of fixture.editing_actions) expect(group.text()).to.contain(action);
		});
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
