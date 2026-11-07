const method = "dinext_timesheets.tests.ui_test_helpers";

function workflowGroup(win) {
	const label = encodeURIComponent(win.__("Workflow"));
	return win.$(`.inner-group-button[data-label="${label}"]`);
}

context("User Timesheet workflow while unsaved", () => {
	before(() => {
		cy.login();
		cy.openDesk("/app");
		cy.call(`${method}.seed_ut_workflow_stop`, { editing_only: 1 }).then((res) => {
			Cypress.env("utWorkflow", res.body.message);
		});
	});

	after(() => {
		cy.login();
		cy.openDesk("/app");
		cy.call(`${method}.cleanup_ut_workflow_stop`);
	});

	it("hides Workflow while Not Saved and shows it again after reload", () => {
		const { name, user, password } = Cypress.env("utWorkflow");
		cy.login(user, password);
		cy.visit(`/app/user-timesheet/${encodeURIComponent(name)}`);
		cy.window().should((win) => {
			expect(workflowGroup(win).length, "workflow group before edit").to.eq(1);
		});
		cy.window().then((win) => {
			win.cur_frm.dirty();
		});
		cy.window().should((win) => {
			expect(!!win.cur_frm.doc.__unsaved, "unsaved flag").to.eq(true);
			expect(workflowGroup(win).length, "workflow group while unsaved").to.eq(0);
			const pill = win.$(`.indicator-pill:contains("${win.__("Not Saved")}")`);
			expect(pill.length, "Not Saved pill").to.be.greaterThan(0);
		});
		cy.reload();
		cy.window().should((win) => {
			expect(!!win.cur_frm?.doc?.__unsaved, "clean after reload").to.eq(false);
			expect(workflowGroup(win).length, "workflow group after reload").to.eq(1);
		});
	});
});
