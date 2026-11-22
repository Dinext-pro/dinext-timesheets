Cypress.removeAllListeners("uncaught:exception");
const helper = "dinext_timesheets.tests.afl_workflow_comment_ui";
const commentsBanner = ".form-message.dinext-workflow-comments";
const pendingBanner = ".form-message.dinext-pending-approvers";

context("Leave shared approval messages", () => {
	let fixture;

	before(() => {
		cy.login();
		cy.openDesk();
		cy.call(`${helper}.seed_workflow_comment_leave`, {}).its("body.message").then(data => { fixture = data; });
	});

	after(() => {
		cy.login();
		cy.openDesk();
		cy.call(`${helper}.cleanup_workflow_comment_leave`, {});
	});

	for (const language of ["en", "ru"]) {
		it(`keeps the leave approval messages after refresh and a theme change in ${language}`, () => {
			cy.login(fixture.viewers[language], fixture.password);
			cy.openDesk(`/app/application-for-leave/${encodeURIComponent(fixture.leave)}`);
			cy.window().its("frappe.boot.lang").should("eq", language);

			for (const theme of ["dark", "light"]) {
				cy.window().then(win => win.frappe.ui.set_theme(theme));
				cy.document().its("documentElement").invoke("attr", "data-theme").should("eq", theme);
				cy.get(commentsBanner).should("have.length", 1).and("be.visible");
				for (const text of [...fixture.authors, ...fixture.comments]) {
					cy.get(commentsBanner).should("contain.text", text);
				}
				cy.get(pendingBanner).should("have.length", 1).and("contain.text", fixture.pending);
				cy.get(".form-dashboard-section.dinext-pending-approvers").should("not.exist");
				cy.window().then(win => win.cur_frm.reload_doc());
			}
			cy.get(commentsBanner).should("have.length", 1);
		});
	}
});
