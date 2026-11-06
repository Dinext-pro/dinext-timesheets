Cypress.removeAllListeners("uncaught:exception");

const fixtureMethod = "dinext_common.tests.ui_test_helpers";
const rebuildMethod = "dinext_timesheets.workflow_approval.get_timesheet_rebuild_rounds";
const fixture = () => Cypress.env("utRebuild");

function openTimesheet(user, name) {
	cy.login(user, fixture().password);
	cy.intercept(`**/api/method/${rebuildMethod}`).as("rebuildRounds");
	cy.openDesk(`/app/user-timesheet/${encodeURIComponent(name)}`);
	cy.wait("@rebuildRounds").its("response.statusCode").should("eq", 200);
}

function assertPositionRounds() {
	cy.get(".modal:visible").should("not.exist");
	cy.get(".dinext-rebuild-summary")
		.should("have.length", 1)
		.and("be.visible")
		.and("contain", "2")
		.then(($banner) => {
			const rect = $banner[0].getBoundingClientRect();
			const width = $banner[0].ownerDocument.documentElement.clientWidth;
			expect(Math.abs(rect.left)).to.be.lessThan(3);
			expect(Math.abs(rect.right - width)).to.be.lessThan(3);
			expect(rect.height).to.be.at.most(60);
		});
	cy.get(".dinext-rebuild-round, .dinext-pending-approvers").should("not.exist");
}

context("User Timesheet rebuild banner", () => {
	beforeEach(() => cy.viewport(1280, 720));
	before(() => {
		cy.login(Cypress.env("bootstrapUser"), Cypress.env("bootstrapPassword"));
		cy.openDesk("/app");
		cy.call(`${fixtureMethod}.seed_parallel_workflow_cypress`, {}, { timeout: 120000 }).then(
			(res) => {
				Cypress.env("utRebuild", res.body.message);
			}
		);
	});

	after(() => {
		cy.login(Cypress.env("bootstrapUser"), Cypress.env("bootstrapPassword"));
		cy.openDesk("/app");
		cy.call(`${fixtureMethod}.cleanup_parallel_workflow_cypress`, {}, { timeout: 120000 });
	});

	it("keeps only the pending headline for an open timesheet", () => {
		openTimesheet(fixture().approver, fixture().timesheet);
		cy.get(".form-message.blue").should("contain", fixture().approver_b_name);
		cy.get(".dinext-pending-approvers").should("not.exist");
		cy.reload();
		cy.wait("@rebuildRounds");
		cy.get(".form-message.blue").should("contain", fixture().approver_b_name);
		cy.get(".dinext-pending-approvers").should("not.exist");
	});

	it("aggregates every problematic position without offering an approver a reset", () => {
		openTimesheet(fixture().approver, fixture().conflicted_timesheet);
		cy.call(rebuildMethod, { timesheet_name: fixture().conflicted_timesheet }).then((res) => {
			const rounds = res.body.message;
			expect(rounds.map((round) => round.reference_name)).to.have.members([
				fixture().conflicted_position,
				fixture().stalled_position,
			]);
			for (const round of rounds) {
				expect(round.can_reset).to.eq(false);
				expect(round).not.to.have.property("source_title");
			}
		});
		assertPositionRounds();
		cy.get(".dinext-reset-rounds").should("not.exist");
	});

	it("offers System Manager one reset for every position after reload", () => {
		openTimesheet(fixture().manager, fixture().conflicted_timesheet);
		assertPositionRounds();
		cy.get(".dinext-reset-rounds").should("have.length", 1).and("be.visible");
		cy.reload();
		cy.wait("@rebuildRounds");
		assertPositionRounds();
		cy.get(".dinext-reset-rounds").should("have.length", 1).and("be.visible");
	});

	it("keeps the compact orange error readable when the Desk theme changes", () => {
		openTimesheet(fixture().approver, fixture().conflicted_timesheet);
		for (const theme of ["light", "dark"]) {
			cy.window().then((win) => win.frappe.ui.set_theme(theme));
			cy.get("html").should("have.attr", "data-theme", theme);
			assertPositionRounds();
			cy.get(".dinext-rebuild-summary").should(($sections) => {
				for (const section of $sections) {
					const style = section.ownerDocument.defaultView.getComputedStyle(section);
					expect(style.color).not.to.eq(style.backgroundColor);
				}
			});
			cy.screenshot(`timesheet-rebuild-${theme}`, { capture: "viewport" });
		}
	});

	it("shows the error and the single rebuild control in Russian", () => {
		openTimesheet(fixture().manager, fixture().conflicted_timesheet);
		cy.call("frappe.client.set_value", {
			doctype: "User",
			name: fixture().manager,
			fieldname: "language",
			value: "ru",
		});
		openTimesheet(fixture().manager, fixture().conflicted_timesheet);
		assertPositionRounds();
		cy.get(".dinext-rebuild-summary").should("contain", "Нужна пересборка позиций: 2");
		cy.get(".dinext-reset-rounds").should("contain", "Пересобрать все");
		cy.screenshot("timesheet-rebuild-russian", { capture: "viewport" });
	});

	it("keeps the error and one control within a narrow viewport", () => {
		cy.viewport(360, 740);
		openTimesheet(fixture().manager, fixture().conflicted_timesheet);
		assertPositionRounds();
		cy.get(".dinext-reset-rounds")
			.should("have.length", 1)
			.and("be.visible")
			.then(($button) => {
				expect($button[0].getBoundingClientRect().right).to.be.at.most(360);
			});
	});
});
