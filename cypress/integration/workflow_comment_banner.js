Cypress.removeAllListeners("uncaught:exception");
const helper = "dinext_common.tests.required_pending_ui";
const banner = ".form-message.orange.dinext-workflow-comments";
let fixture;

function setComments(mode) {
	cy.call(`${helper}.set_workflow_comments_cypress`, { mode, doctype: "User Timesheet Position" });
	cy.window().then((win) => win.cur_frm.reload_doc());
}

context("Required Workflow comments on timesheet forms", () => {
	before(() => {
		cy.login();
		cy.openDesk("/app");
		cy.call(`${helper}.seed_required_pending_cypress`, {}, { timeout: 180000 })
			.then((res) => { fixture = res.body.message; });
	});
	after(() => {
		cy.login();
		cy.openDesk("/app");
		cy.call(`${helper}.cleanup_required_pending_cypress`, {}, { timeout: 180000 });
	});
	beforeEach(() => {
		cy.login(fixture.viewer, fixture.password);
		cy.openDesk("/app");
		cy.call(`${helper}.set_workflow_comments_cypress`, { mode: "empty", doctype: "User Timesheet Position" });
		cy.openDesk(`/app/user-timesheet/${encodeURIComponent(fixture.timesheet)}`);
		cy.get(".dinext-pending-approvers").should("be.visible");
	});

	it("shows every position's comments when another approver chooses a transition without a comment", () => {
		setComments("mixed");
		cy.get(banner).should("be.visible").and("contain", fixture.required).and("contain", fixture.mixed)
			.and("contain", fixture.positions[0]).and("contain", fixture.positions[1]);
		cy.get(`${banner} .dinext-workflow-comment-row`).should("have.length", 4);
	});

	it("clears comments superseded by newer rounds without removing pending approvers", () => {
		setComments("multiple");
		cy.get(banner).should("be.visible");
		setComments("later");
		cy.get(banner).should("not.exist");
		cy.get(".dinext-pending-approvers").should("be.visible");
	});

	it("preserves comments, pending, overdue and unrelated messages during repeated refresh", () => {
		cy.intercept("POST", "**/api/method/dinext_timesheets.deadlines.get_deadline_state", {
			body: { message: { overdue: true, deadline: "2026-10-01" } },
		});
		setComments("multiple");
		cy.get(banner).should("be.visible");
		cy.window().then(async (win) => {
			win.cur_frm.dashboard.add_comment("Other timesheet message", "orange", true);
			await win.UserTimesheet.showTimesheetDashboard(win.cur_frm);
			await win.UserTimesheet.showTimesheetDashboard(win.cur_frm);
		});
		for (const theme of ["dark", "light"]) {
			cy.window().then((win) => win.frappe.ui.set_theme(theme));
			cy.get(banner).should("have.length", 1).and("be.visible");
			cy.get(".dinext-pending-approvers").should("have.length", 1).and("be.visible");
			cy.get(".dinext-timesheet-deadline").should("have.length", 1).and("be.visible");
			cy.contains(".form-message.orange", "Other timesheet message").should("be.visible");
		}
	});
});
