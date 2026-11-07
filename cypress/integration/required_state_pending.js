Cypress.removeAllListeners("uncaught:exception");
const helper = "dinext_common.tests.required_pending_ui";
const pendingApi = "dinext_common.workflow_approval.api.get_pending_approvers";
const banner = ".form-message.blue.dinext-pending-approvers";
let fixture;

function setOptional(value) {
	return cy.call(`${helper}.set_required_pending_optional`, {
		doctype: "User Timesheet Position",
		optional: value,
	});
}
function assertNames() {
	cy.get(banner)
		.should("be.visible")
		.and("contain", fixture.required)
		.and("contain", fixture.mixed)
		.and("not.contain", fixture.optional);
	cy.get(banner).should("have.length", 1).and("not.contain", fixture.viewer_name);

	cy.window().should((win) => {
		const rows = win.cur_frm.ut.rows.filter((row) => row.rowType === "position");
		const first = rows.find((row) => row.id === fixture.positions[0]);
		const second = rows.find((row) => row.id === fixture.positions[1]);
		expect(first.approver_tooltip).to.contain(fixture.required).and.contain(fixture.mixed);
		expect(first.approver_tooltip)
			.not.to.contain(fixture.optional)
			.and.not.to.contain(fixture.viewer_name);
		expect(second.approver_tooltip).to.contain(fixture.mixed);
		expect(second.approver_tooltip)
			.not.to.contain(fixture.required)
			.and.not.to.contain(fixture.optional)
			.and.not.to.contain(fixture.viewer_name);
	});
}
function assertEmpty() {
	cy.get(banner).should("not.exist");

	cy.window().should((win) => {
		for (const row of win.cur_frm.ut.rows.filter((row) => row.rowType === "position"))
			expect(row.approver_tooltip).to.eq("");
	});
}
function readPending() {
	return cy.call(pendingApi, { doctype: "User Timesheet", name: fixture.timesheet });
}

function readActions() {
	return cy
		.call("dinext_timesheets.workflow_approval.get_timesheet_position_actions", {
			timesheet_name: fixture.timesheet,
		})
		.then((res) => res.body.message.actions.map((row) => row.action));
}

context("Mandatory target pending actors timesheet", () => {
	before(() => {
		cy.login();
		cy.openDesk("/app");
		cy.call(`${helper}.seed_required_pending_cypress`, {}, { timeout: 180000 }).then((res) => {
			fixture = res.body.message;
		});
	});
	after(() => {
		cy.login();
		cy.openDesk("/app");
		cy.call(`${helper}.cleanup_required_pending_cypress`, {}, { timeout: 180000 });
	});
	beforeEach(() => {
		cy.login(fixture.viewer, fixture.password);
		cy.openDesk("/app");
		setOptional(0);
		cy.openDesk(`/app/user-timesheet/${encodeURIComponent(fixture.timesheet)}`);
		cy.window().should((win) => expect(win.cur_frm?.doc?.name).to.eq(fixture.timesheet));
	});

	it("shows mandatory-only and mixed actors using personal target states", () => {
		assertNames();
		cy.window().then((win) => win.frappe.ui.set_theme("dark"));
		assertNames();
		cy.window().then((win) => win.frappe.ui.set_theme("light"));
		assertNames();
		cy.screenshot("required-pending-timesheet", { capture: "viewport" });
	});

	it("clears the pending display when all targets become optional", () => {
		let actions;
		readActions().then((value) => {
			actions = value;
		});
		assertNames();
		setOptional(1);
		cy.window().then((win) => win.cur_frm.reload_doc());
		readPending().then((res) => {
			expect(res.body.message).to.have.length(0);
		});
		assertEmpty();
		readActions().then((value) => expect(value).to.deep.eq(actions));
	});

	it("reflects a changed checkbox on an existing round without rebuilding it", () => {
		let original;
		readPending().then((res) => {
			original = JSON.stringify(res.body.message);
		});
		setOptional(1);
		cy.window().then((win) => win.cur_frm.reload_doc());
		assertEmpty();
		setOptional(0);
		cy.window().then((win) => win.cur_frm.reload_doc());
		assertNames();
		readPending().then((res) => expect(JSON.stringify(res.body.message)).to.eq(original));
	});

	it("clears the parent headline and tooltips when only the viewer is pending", () => {
		assertNames();
		cy.intercept("POST", `**/api/method/${pendingApi}`, (req) => {
			req.continue((res) => {
				res.body.message = res.body.message.filter((row) => row.approver === fixture.viewer);
			});
		}).as("onlySelf");
		cy.window().then((win) => win.UserTimesheet.showTimesheetDashboard(win.cur_frm));
		cy.wait("@onlySelf");
		assertEmpty();
	});

	it("keeps one owned pending and overdue message while preserving another message", () => {
		cy.intercept("POST", "**/api/method/dinext_timesheets.deadlines.get_deadline_state", {
			body: { message: { overdue: true, deadline: "2026-10-01" } },
		});
		assertNames();
		cy.window().then(async (win) => {
			win.cur_frm.dashboard.add_comment("Other timesheet message", "yellow", true);
			await win.UserTimesheet.showTimesheetDashboard(win.cur_frm);
			await win.UserTimesheet.showTimesheetDashboard(win.cur_frm);
		});
		assertNames();
		cy.contains(".form-message.yellow", "Other timesheet message").should("be.visible");
		cy.get(".form-message.orange.dinext-timesheet-deadline")
			.should("have.length", 1).and("be.visible");
	});

	it("shows pending approvers together with a position rebuild banner", () => {
		assertNames();
		cy.intercept("POST", "**/api/method/dinext_timesheets.workflow_approval.get_timesheet_rebuild_rounds", {
			body: { message: [{
				round_id: "cypress-position-conflict",
				round_status: "Conflicted",
				reference_name: fixture.positions[1],
				source_title: fixture.positions[1],
				can_reset: false,
			}] },
		}).as("rebuildWithPending");
		cy.window().then((win) => win.UserTimesheet.showTimesheetDashboard(win.cur_frm));
		cy.wait("@rebuildWithPending");
		assertNames();
		cy.get(".dinext-rebuild-summary").should("have.length", 1).and("be.visible");
	});
});
