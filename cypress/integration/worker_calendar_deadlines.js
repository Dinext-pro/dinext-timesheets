const helper = "dinext_timesheets.tests.deadline_ui";
let fixture;

function loginAuthor() {
	cy.login(fixture.user, fixture.password);
	cy.openDesk(`/app/user-timesheet/${encodeURIComponent(fixture.timesheet)}`);
}

function assertOverdueList() {
	cy.window().should(win => {
		expect(win.cur_list?.doctype).to.eq("User Timesheet");
	});
	cy.get(".list-row-container").should("have.length", 1).and("contain.text", fixture.timesheet);
	cy.get(".list-row-container").should("not.contain.text", fixture.empty).and("not.contain.text", fixture.pending);
}

function openNewForm(doctype) {
	cy.window().then(win => {
		return win.frappe.model.with_doctype(doctype).then(() => {
			const doc = win.frappe.model.get_new_doc(doctype);
			return win.frappe.set_route("Form", doctype, doc.name);
		});
	});
	cy.window().should(win => {
		expect(win.frappe.get_route()[1]).to.eq(doctype);
		expect(win.frappe.views.formview[doctype]?.frm.doc.doctype).to.eq(doctype);
	});
}

context("Worker calendar timesheet deadlines", () => {
	before(() => {
		cy.task("deadlineCheckpoint", "bootstrap login");
		cy.login(); cy.openDesk("/app");
		cy.task("deadlineCheckpoint", "seed fixtures");
		cy.call(`${helper}.seed_deadline_ui`).then(res => { fixture = res.body.message; });
	});
	beforeEach(() => cy.task("deadlineCheckpoint", Cypress.currentTest.title));
	after(() => {
		if (!fixture) return;
		cy.login(); cy.openDesk("/app");
		cy.call(`${helper}.cleanup_deadline_ui`, { user: fixture.user });
	});

	it("recalculates on an actual form save and reads overdue independently of the old flag", () => {
		loginAuthor();
		cy.openDesk(`/app/user-timesheet/${encodeURIComponent(fixture.timesheet)}`);
		cy.window().should(win => expect(win.cur_frm?.doc.name).to.eq(fixture.timesheet));
		cy.intercept("POST", "**/api/method/frappe.desk.form.save.savedocs").as("saveDeadline");
		cy.window().then(win => win.cur_frm.set_value("ts_valid_for", fixture.next_period_end).then(() => win.cur_frm.save()));
		cy.wait("@saveDeadline").its("response.statusCode").should("eq", 200);
		cy.call("dinext_timesheets.deadlines.get_deadline_state", { name: fixture.timesheet }).then(res => {
			expect(res.body.message).to.deep.eq({ deadline: fixture.next_deadline, overdue: true });
			fixture.deadline = fixture.next_deadline;
		});
		cy.get(".form-message:visible").should("contain.text", "Submission deadline");
	});

	for (const language of ["en", "ru"]) for (const theme of ["light", "dark"]) {
		it(`shows matching form/card/list in ${language}, ${theme} theme`, () => {
			loginAuthor();
			cy.call(`${helper}.set_deadline_language`, { language });
			cy.openDesk(`/app/user-timesheet/${encodeURIComponent(fixture.timesheet)}`);
			cy.window().then(win => win.frappe.ui.set_theme(theme));
			cy.get(".form-message:visible").should("contain.text", language === "ru" ? "Срок отправки" : "Submission deadline");
			cy.screenshot(`deadline-form-${language}-${theme}`, { capture: "viewport" });
			cy.openDesk("/app/" + encodeURIComponent("мои-таймшиты"));
			cy.window().then(win => win.frappe.ui.set_theme(theme));
			cy.contains(".number-widget-box", /просроч|overdue/i).as("overdueCard");
			cy.get("@overdueCard").find(".number").should("have.text", "1");
			cy.screenshot(`deadline-card-${language}-${theme}`, { capture: "viewport" });
			cy.get("@overdueCard").find(".widget-body").click();
			assertOverdueList();
			for (const doctype of ["Task", "Issue"]) {
				cy.window().then(win => win.localStorage.removeItem(`${win.location.host}:${fixture.user}:timesheet-overdue-until`));
				openNewForm(doctype);
				cy.get(".modal:visible").should("contain.text", language === "ru" ? "Просроченные таймшиты" : "Overdue Timesheets");
				cy.screenshot(`deadline-${doctype.toLowerCase()}-${language}-${theme}`, { capture: "viewport" });
				cy.contains(".modal:visible button", language === "ru" ? "Перейти к таймшитам" : "Go to Timesheets").click();
				assertOverdueList();
			}
		});
	}

	it("shares the thirty-minute postpone between Task and Issue", () => {
		loginAuthor();
		cy.openDesk(`/app/user-timesheet/${encodeURIComponent(fixture.timesheet)}`);
		cy.clock(Date.now(), ["Date"]);
		cy.window().then(win => win.localStorage.removeItem(`${win.location.host}:${fixture.user}:timesheet-overdue-until`));
		openNewForm("Task");
		cy.contains(".modal:visible", /Overdue Timesheets|Просроченные таймшиты/).should("be.visible");
		cy.screenshot("deadline-task-reminder", { capture: "viewport" });
		cy.contains(".modal:visible button", /Remind Me Later|Напомнить позже/).click();
		openNewForm("Issue");
		cy.window().then(win => win.frappe.after_ajax());
		cy.get(".modal:visible").should("not.exist");
		cy.tick(30 * 60 * 1000 - 1);
		cy.window().then(win => win.frappe.views.formview.Issue.frm.refresh());
		cy.get(".modal:visible").should("not.exist");
		cy.tick(1);
		cy.window().then(win => win.frappe.views.formview.Issue.frm.refresh());
		cy.contains(".modal:visible", /Overdue Timesheets|Просроченные таймшиты/).should("be.visible");
		cy.screenshot("deadline-issue-reminder", { capture: "viewport" });
		cy.contains(".modal:visible button", /Go to Timesheets|Перейти к таймшитам/).click();
		assertOverdueList();
	});
});
