Cypress.removeAllListeners("uncaught:exception");

const helpers = "dinext_timesheets.tests.ui_test_helpers";
const applyMethod = "dinext_timesheets.workflow_approval.apply_timesheet_position_action";
let fixture;

function openTimesheet(blockOne) {
	cy.login();
	cy.openDesk("/app");
	cy.call(
		`${helpers}.seed_ut_position_batch`,
		{ block_one: blockOne },
		{ timeout: 120000 }
	).then((res) => {
		fixture = res.body.message;
		cy.login(fixture.user, fixture.password);
		cy.openDesk(`/app/user-timesheet/${encodeURIComponent(fixture.name)}`);
		cy.window().should((win) => {
			expect(win.cur_frm?.doc?.name).to.eq(fixture.name);
			expect(Boolean(win.cur_frm?._ut_load_promise)).to.eq(false);
			const group = win.$(
				`.inner-group-button[data-label="${encodeURIComponent(win.__("Workflow"))}"]`
			);
			expect(group.text()).to.include(fixture.action);
		});
	});
}

function applyAction() {
	cy.intercept("POST", `**/api/method/${applyMethod}`).as("applyPositions");
	cy.window().then((win) => {
		cy.spy(win.frappe, "show_progress").as("positionProgress");
		const group = `.inner-group-button[data-label="${encodeURIComponent(
			win.__("Workflow")
		)}"]`;
		cy.get(`${group} button`).first().click();
		cy.contains(`${group} .dropdown-menu a`, fixture.action).click();
	});
}

context("User Timesheet position batch result", () => {
	after(() => {
		cy.login();
		cy.openDesk("/app");
		cy.call(`${helpers}.cleanup_ut_position_batch`, {}, { timeout: 120000 });
	});

	it("shows one localized result after refreshing and unlocking the affected card", () => {
		openTimesheet(1);
		let releaseRefresh;
		let refreshPending = false;
		let failure;
		const refreshGate = new Promise((resolve) => {
			releaseRefresh = resolve;
		});
		cy.then(() => {
			cy.intercept(
				{
					method: "GET",
					pathname: "/api/method/frappe.desk.form.load.getdoc",
					query: { doctype: "User Timesheet", name: fixture.name },
				},
				(req) => {
					req.continue(() => {
						refreshPending = true;
						return refreshGate;
					});
				}
			).as("refreshTimesheet");
		});
		applyAction();
		cy.wait("@applyPositions").then(({ response }) => {
			expect(response.statusCode).to.eq(200);
			const outcome = response.body.message;
			expect(outcome.processed).to.eq(2);
			expect(outcome.results).to.have.length(1);
			expect(outcome.failed).to.have.length(1);
			[failure] = outcome.failed;
			expect(failure.name).to.eq(fixture.blocked);
			expect(failure.workflow_error).to.include({
				code: "no_eligible_approvers",
				workflow: fixture.workflow,
				state: "Rejected",
			});
			expect(failure.error).to.include(fixture.follow_up);
		});
		cy.wrap(null).should(() => expect(refreshPending).to.eq(true));
		cy.get("@positionProgress").should(
			"have.been.calledWith",
			Cypress.sinon.match.string,
			2,
			2
		);
		cy.get(".modal:visible .progress").should("be.visible");
		cy.contains(".modal:visible", "Не удалось обработать позиции таймшита").should(
			"not.exist"
		);
		cy.window().should((win) => expect(win.cur_frm.page.wrapper[0].inert).to.eq(true));
		cy.then(releaseRefresh);
		cy.wait("@refreshTimesheet").its("response.statusCode").should("eq", 200);
		cy.get(".modal:visible", { timeout: 20000 }).should(($dialogs) => {
			expect($dialogs).to.have.length(1);
			expect($dialogs.text()).to.include("Не удалось обработать позиции таймшита");
			expect($dialogs.text()).to.include("Успешно обработано позиций: 1 из 2");
			expect($dialogs.find("li strong").text()).to.eq(
				`Позиция 2 · ${fixture.labels.project} · ${fixture.labels.tasks[1]} · ${fixture.labels.role}`
			);
			expect($dialogs.text()).to.include("Нет согласующих для переходов");
			expect($dialogs.text()).to.include(fixture.follow_up);
			expect($dialogs.text()).not.to.include(failure.name);
		});
		cy.get(".modal:visible .progress, #freeze").should("not.exist");
		cy.window().should((win) => expect(win.cur_frm.page.wrapper[0].inert).to.eq(false));
		cy.screenshot("timesheet-position-workflow-error", { capture: "viewport" });
	});

	it("ends progress without a result dialog when every position succeeds", () => {
		openTimesheet(0);
		applyAction();
		cy.wait("@applyPositions").then(({ response }) => {
			expect(response.statusCode).to.eq(200);
			expect(response.body.message.results).to.have.length(2);
			expect(response.body.message.failed).to.deep.eq([]);
		});
		cy.get("@positionProgress").should(
			"have.been.calledWith",
			Cypress.sinon.match.string,
			2,
			2
		);
		cy.window().should((win) => expect(win.cur_frm.page.wrapper[0].inert).to.eq(false));
		cy.get(".modal:visible, #freeze, .modal-backdrop").should("not.exist");
	});
});
