const method = "dinext_timesheets.tests.ui_test_helpers";

context("User Timesheet form positions table", () => {
	before(() => {
		cy.login();
		cy.openDesk("/app");
		cy.call(`${method}.seed_ut_form_table`).then((res) => {
			Cypress.env("utForm", res.body.message);
		});
	});

	after(() => {
		cy.login();
		cy.openDesk("/app");
		cy.call(`${method}.cleanup_ut_form_table`);
	});

	it("shows the DinextTable and not the legacy flex grid", () => {
		const name = Cypress.env("utForm").name;
		cy.login();
		cy.visit(`/app/user-timesheet/${encodeURIComponent(name)}`);
		cy.get(".user-timesheet-table", { timeout: 120000 }).should("exist");
		cy.get("#timesheet-table").should("not.exist");
	});
});
