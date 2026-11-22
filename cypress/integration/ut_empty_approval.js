const fixtureMethod = "dinext_timesheets.tests.empty_timesheet_ui";
const applyMethod = "dinext_timesheets.workflow_approval.apply_timesheet_position_action";

function clickWorkflowAction(action) {
	cy.window().then((win) => {
		const group = `.inner-group-button[data-label="${encodeURIComponent(win.__("Workflow"))}"]`;
		cy.get(`${group} button`).click();
		const label = Cypress._.escapeRegExp(win.__(action));
		cy.contains(`${group} .dropdown-menu a`, new RegExp(`^\\s*${label}\\s*$`, "u")).click();
	});
}

describe("Empty timesheet workflow", () => {
	let fixture;

	before(() => {
		cy.login();
		cy.openDesk("/app");
		cy.call(`${fixtureMethod}.seed`).then(({ body }) => {
			fixture = body.message;
		});
	});

	after(() => {
		if (fixture) {
			cy.login();
			cy.openDesk("/app");
			cy.call(`${fixtureMethod}.cleanup`, { name: fixture.name });
		}
	});

	it("hides unsaved actions and approves and reopens a saved empty timesheet", () => {
		cy.then(() => {
			cy.login(fixture.user, fixture.password);
			cy.openDesk(`/app/user-timesheet/${encodeURIComponent(fixture.name)}`);
		});
		cy.window().should((win) => {
			const menu = win.cur_frm?.page.get_inner_group_button(win.__("Workflow"));
			expect(menu?.text()).to.contain(win.__("Approve"));
		});
		cy.window().then((win) => win.cur_frm.dirty());
		cy.window().should((win) => {
			const menu = win.cur_frm.page.get_inner_group_button(win.__("Workflow"));
			expect(menu?.text() || "").not.to.contain(win.__("Approve"));
		});
		cy.reload();
		cy.window().should((win) => {
			const menu = win.cur_frm?.page.get_inner_group_button(win.__("Workflow"));
			expect(menu?.text()).to.contain(win.__("Approve"));
		});

		cy.intercept("POST", `**/api/method/${applyMethod}`).as("transition");
		clickWorkflowAction("Approve");
		cy.wait("@transition").should(({ request, response }) => {
			const args = typeof request.body === "string"
				? Object.fromEntries(new URLSearchParams(request.body))
				: request.body;
			expect(args.scope).to.equal("timesheet");
			expect(response.statusCode).to.equal(200);
		});
		cy.window().should((win) => {
			expect(win.cur_frm?.doc.ut_status).to.eq("Approved");
			expect(win.cur_frm.doc.ut_approval_date).to.be.a("string").and.not.be.empty;
			const menu = win.cur_frm.page.get_inner_group_button(win.__("Workflow"));
			expect(menu?.text()).to.contain(win.__("Return to Editing"));
		});

		clickWorkflowAction("Return to Editing");
		cy.window().then((win) => {
			cy.get(".modal:visible").contains("button", win.__("Continue")).click();
		});
		cy.wait("@transition").its("response.statusCode").should("eq", 200);
		cy.window().should((win) => {
			expect(win.cur_frm?.doc.ut_status).to.eq("Rework");
			expect(win.cur_frm.doc.ut_approval_date ?? "").to.eq("");
			const menu = win.cur_frm.page.get_inner_group_button(win.__("Workflow"));
			expect(menu?.text()).to.contain(win.__("Approve"));
		});
	});
});
