const fixtureMethod = "dinext_timesheets.tests.timesheet_team_lead_ui";
const actionsMethod = "dinext_timesheets.workflow_approval.get_timesheet_position_actions";
const applyMethod = "dinext_timesheets.workflow_approval.apply_timesheet_position_action";
let requestNumber = 0;

function pendingRounds(name) {
	return cy.call("dinext_common.workflow_approval.api.get_pending_approvers", {
		doctype: "User Timesheet", name,
	}).its("body.message").then((rows) => rows
		.filter((row) => row.workflow_state === "Pending Approval")
		.map((row) => row.approval_round_id));
}

function positions(name) {
	return cy.call("frappe.client.get_list", {
		doctype: "User Timesheet Position",
		filters: { user_timesheet: name },
		fields: ["name", "status", "user"],
	}).its("body.message");
}

function openForm(name, state, editable) {
	cy.openDesk(`/app/user-timesheet/${encodeURIComponent(name)}`);
	cy.window().should((win) => {
		expect(win.cur_frm?.doc?.name).to.eq(name);
		expect(win.cur_frm?.doc?.ut_status).to.eq(state);
		expect(win.cur_frm?.ut?.canEdit).to.eq(editable);
	});
}

function transition(name, action, state, editable, { comment, confirm } = {}) {
	cy.call(actionsMethod, { timesheet_name: name }).then(({ body }) => {
		expect(body.message.actions.map((entry) => entry.action)).to.include(action);
	});
	const alias = `positionAction${++requestNumber}`;
	cy.intercept("POST", `**/api/method/${applyMethod}`).as(alias);
	cy.window().then((win) => {
		const selector = `.inner-group-button[data-label="${encodeURIComponent(win.__("Workflow"))}"]`;
		cy.get(selector).find("button").first().click();
		cy.get(selector).find(".dropdown-menu").contains("a", win.__(action)).click();
	});
	if (confirm) {
		cy.get(".modal:visible .modal-footer .btn-danger").click();
	}
	if (comment) {
		cy.get('.modal:visible textarea[data-fieldname="comment"]').should("be.visible");
		cy.window().should((win) => expect(win.cur_dialog?.fields_dict?.comment).to.exist)
			.then((win) => win.cur_dialog.set_value("comment", comment));
		cy.window().should((win) => expect(win.cur_dialog.get_value("comment")).to.eq(comment));
		cy.get(".modal:visible .modal-footer .btn-primary").click();
	}
	cy.wait(`@${alias}`).its("response.statusCode").should("eq", 200);
	cy.window().should((win) => {
		expect(win.cur_frm?.doc?.ut_status).to.eq(state);
		expect(win.cur_frm?.ut?.canEdit).to.eq(editable);
	});
}

describe("Delegated User Timesheet", () => {
	let fixture;
	let name;

	before(() => {
		cy.login();
		cy.openDesk("/app");
		cy.call(`${fixtureMethod}.seed`).then(({ body }) => {
			fixture = body.message;
		});
	});

	after(() => {
		cy.login();
		cy.openDesk("/app");
		cy.call(`${fixtureMethod}.cleanup`);
	});

	it("lets the assigned lead create, withdraw, correct and resubmit through position Workflow", () => {
		cy.login(fixture.former, fixture.password);
		cy.openDesk("/app");
		cy.call("dinext_timesheets.dinext_timesheets.user_timesheet.api.get_timesheet_context", {
			worker: fixture.worker, start: fixture.start,
		}, { failOnStatusCode: false }).its("status").should("eq", 403);

		cy.login(fixture.lead, fixture.password);
		cy.openDesk("/app");
		cy.window().then((win) => win.frappe.new_doc("User Timesheet"));
		cy.window().should((win) => expect(win.cur_frm?.doctype).to.eq("User Timesheet"));
		cy.window().then(async (win) => {
			const frm = win.cur_frm;
			await frm.set_value("timesheet_from", fixture.worker);
			await frm.set_value("ts_valid_from", fixture.start);
			await frm.save();
		});
		cy.window().should((win) => {
			expect(Boolean(win.cur_frm?.is_new())).to.eq(false);
			expect(win.cur_frm?.doc?.timesheet_from).to.eq(fixture.worker);
			expect(win.cur_frm?.doc?.ts_valid_for).to.eq(fixture.end);
		}).then((win) => {
			name = win.cur_frm.doc.name;
			return cy.call("frappe.client.insert_many", {
				docs: fixture.tasks.map((task) => ({
					doctype: "User Timesheet Position",
					user_timesheet: name, user: fixture.worker,
					project: fixture.project, project_role: fixture.role,
					document_type: "Task", document_name: task,
					table: [{ date: fixture.start, hours: 1, description: "Initial work" }],
				})),
			});
		});

		cy.then(() => {
			openForm(name, "Draft", true);
			positions(name).then((rows) => {
				expect(rows).to.have.length(2);
				expect(rows.every((row) => row.user === fixture.worker)).to.eq(true);
			});
			transition(name, fixture.actions.submit, "Pending Approval", false);
			cy.call(actionsMethod, { timesheet_name: name }).its("body.message.actions").then((rows) => {
				expect(rows.map((row) => row.action)).not.to.include(fixture.actions.approve);
			});
			let firstRound;
			pendingRounds(name).then((rounds) => {
				expect(rounds).not.to.be.empty;
				firstRound = rounds;
			});
			transition(name, fixture.actions.withdraw, "Rework", true);
			pendingRounds(name).should("be.empty");
			transition(name, fixture.actions.submit, "Pending Approval", false);
			pendingRounds(name).then((rounds) => {
				expect(rounds).not.to.be.empty;
				expect(rounds.filter((round) => firstRound.includes(round))).to.be.empty;
			});
		});

		cy.then(() => {
			cy.login(fixture.approver, fixture.password);
			openForm(name, "Pending Approval", false);
			transition(name, fixture.actions.reject, "Rejected", false, { comment: "Explain the second task" });
		});

		cy.then(() => {
			cy.login(fixture.lead, fixture.password);
			openForm(name, "Rejected", false);
			cy.window().should((win) => {
				expect(win.cur_frm.ts_positions?.some((row) =>
					row.reject_reason?.includes("Explain the second task")
				)).to.eq(true);
			});
			transition(name, fixture.actions.revise, "Rework", true);
			positions(name).then(([position]) => {
				cy.call("frappe.client.get", {
					doctype: "User Timesheet Position", name: position.name,
				}).then(({ body }) => {
					const doc = body.message;
					doc.table[0].description = "Explained the work";
					return cy.call("frappe.client.save", { doc });
				});
			});
			openForm(name, "Rework", true);
			cy.window().should((win) => {
				expect(win.cur_frm.ts_positions?.some((row) =>
					row.details.some((day) => day.description === "Explained the work")
				)).to.eq(true);
			});
			transition(name, fixture.actions.submit, "Pending Approval", false);
			cy.login(fixture.approver, fixture.password);
			openForm(name, "Pending Approval", false);
			transition(name, fixture.actions.approve, "Approved", false);
			cy.login(fixture.lead, fixture.password);
			openForm(name, "Approved", false);
			transition(name, fixture.actions.reopen, "Rework", true, { confirm: true });
		});
	});
});
