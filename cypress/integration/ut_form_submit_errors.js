const method = "dinext_timesheets.tests.ui_test_helpers";
const limitsMethod =
	"**/api/method/project_workload_assignment.api.calculate_user_timesheet_limits";
const DATE = "2026-09-03";
const DAY = `day_${DATE}`;

function workflowGroup(win) {
	const label = encodeURIComponent(win.__("Workflow"));
	return win.$(`.inner-group-button[data-label="${label}"]`);
}

function limitsOk() {
	return { statusCode: 200, body: { message: [] } };
}

let limitsReply = limitsOk;

function row(extra) {
	return {
		id: "row-1",
		rowType: "position",
		project: "PROJ-1",
		document_type: "Task",
		document_name: "TASK-1",
		document_label: "Task One",
		project_role: "Developer",
		isNew: false,
		[DAY]: 8,
		[`desc_${DATE}`]: "did the work",
		...extra,
	};
}

function arm(win, options) {
	const frm = win.cur_frm;
	frm.deletedPositions = options.deleted || [];
	frm.template_doc = options.template || {
		hours_on_date: 8,
		minimum_hours: 0,
		maximum_hours: 0,
		_is_mandatory: false,
	};
	frm.ut.dates = options.dates || [DATE];
	frm.ut.holidays = options.holidays || [];
	frm.ut.workHours = [];
	frm.ut.rows = options.rows;
	if (options.positions) {
		frm.ts_positions = options.positions;
	}
	if (options.addNewPosition) {
		frm.ts_positions = (frm.ts_positions || []).concat([
			{ name: "new_1", new: true },
		]);
	}
}

function openForm() {
	const name = Cypress.env("utWorkflow").name;
	cy.login();
	cy.visit(`/app/user-timesheet/${encodeURIComponent(name)}`);
	cy.get(".user-timesheet-table", { timeout: 120000 }).should("exist");
	cy.window({ timeout: 120000 }).should((win) => {
		expect(workflowGroup(win).length, "workflow group").to.eq(1);
		expect(!!win.cur_frm.doc.__unsaved, "saved form").to.eq(false);
	});
}

function clickSubmit() {
	cy.window().then((win) => {
		const action = Cypress.env("submitAction");
		const label =
			win.frappe.dinext?.workflowActionLabel?.(action) || win.__(action);
		const encoded = encodeURIComponent(label);
		const item = win.$(`.dropdown-item[data-label="${encoded}"]`);
		expect(item.length, "submit action").to.eq(1);
		item.trigger("click");
	});
}

function expectDialog(text) {
	cy.get(".msgprint", { timeout: 20000 }).should("contain", text);
}

function expectCell(rowId, field, text) {
	cy.window().should((win) => {
		const message = win.cur_frm.ut.invalidCells?.get?.(`${rowId}::${field}`) || "";
		expect(message, `${rowId} ${field}`).to.contain(text);
	});
}

context("User Timesheet submit errors", () => {
	before(() => {
		cy.login();
		cy.openDesk("/app");
		cy.call(`${method}.seed_ut_workflow_button`).then((res) => {
			const seeded = res.body.message;
			Cypress.env("utWorkflow", seeded);
			return cy.call(
				"dinext_timesheets.workflow_approval.get_timesheet_position_actions",
				{ timesheet_name: seeded.name }
			);
		}).then((res) => {
			const submit = (res.body.message.actions || []).find(
				(row) => row.runs_timesheet_checks
			);
			expect(submit, "submit action runs timesheet checks").to.exist;
			Cypress.env("submitAction", submit.action);
		});
	});

	after(() => {
		cy.login();
		cy.openDesk("/app");
		cy.call(`${method}.cleanup_ut_workflow_button`);
	});

	beforeEach(() => {
		limitsReply = limitsOk;
		cy.intercept("POST", limitsMethod, (req) => {
			req.reply(limitsReply());
		});
		openForm();
	});

	it("asks to save a new position before submission", () => {
		cy.window().then((win) => {
			arm(win, { rows: win.cur_frm.ut.rows, addNewPosition: true });
			expect(!!win.cur_frm.is_dirty(), "form stays saved").to.eq(false);
		});
		clickSubmit();
		cy.window().then((win) => {
			expectDialog(win.__("Save the timesheet first"));
		});
	});

	it("requires a project and marks the project cell", () => {
		cy.window().then((win) => {
			arm(win, { rows: [row({ project: "" })] });
		});
		clickSubmit();
		cy.window().then((win) => {
			const text = win.__("Select a project in row {0}", [1]);
			expectDialog(text);
			expectCell("row-1", "project_label", text);
		});
	});

	it("requires a task and marks the task cell", () => {
		cy.window().then((win) => {
			arm(win, { rows: [row({ document_name: "" })] });
		});
		clickSubmit();
		cy.window().then((win) => {
			const text = win.__("Select a request or task in row {0}", [1]);
			expectDialog(text);
			expectCell("row-1", "document_label", text);
		});
	});

	it("requires a project role and marks the role cell", () => {
		cy.window().then((win) => {
			arm(win, { rows: [row({ project_role: "" })] });
		});
		clickSubmit();
		cy.window().then((win) => {
			const text = win.__("Select a project role in row {0}", [1]);
			expectDialog(text);
			expectCell("row-1", "project_role", text);
		});
	});

	it("requires hours and marks the total", () => {
		cy.window().then((win) => {
			arm(win, {
				rows: [row({ [DAY]: 0, [`desc_${DATE}`]: "" })],
				holidays: [{ holiday_date: DATE }],
			});
		});
		clickSubmit();
		cy.window().then((win) => {
			const text = win.__("Enter hours in row {0}", [1]);
			expectDialog(text);
			expectCell("row-1", "total", text);
		});
	});

	it("requires a description when the template says so", () => {
		cy.window().then((win) => {
			arm(win, {
				rows: [row({ [`desc_${DATE}`]: "" })],
				template: {
					hours_on_date: 8,
					minimum_hours: 0,
					maximum_hours: 0,
					_is_mandatory: true,
				},
			});
		});
		clickSubmit();
		cy.window().then((win) => {
			const text = win.__(
				"Description is not filled for {0} on task {1}",
				[DATE, "Task One"]
			);
			expectDialog(text);
			expectCell("row-1", DAY, text);
		});
	});

	it("rejects two rows with the same project, task, and role", () => {
		cy.window().then((win) => {
			arm(win, {
				rows: [
					row({ id: "row-1", [DAY]: 4 }),
					row({ id: "row-2", [DAY]: 4 }),
				],
			});
		});
		clickSubmit();
		cy.window().then((win) => {
			const text = win.__("Duplicate rows {0}: same project, task, and role", [
				"1, 2",
			]);
			expectDialog(text);
			expectCell("row-1", "project_label", text);
			expectCell("row-2", "document_label", text);
		});
	});

	it("asks for positions when a working day has none", () => {
		cy.window().then((win) => {
			arm(win, { rows: [], positions: [] });
		});
		clickSubmit();
		cy.window().then((win) => {
			expectDialog(win.__("Add positions for approval"));
		});
	});

	it("rejects a day below the minimum and marks the total row", () => {
		cy.window().then((win) => {
			arm(win, { rows: [row({ [DAY]: 1 })] });
		});
		clickSubmit();
		cy.window().then((win) => {
			const text = win.__("{0} cannot be less than {1} hours.", [DATE, 8]);
			expectDialog(text);
			expectCell("ut_day_totals", DAY, text);
		});
	});

	it("rejects a day above the maximum and marks the total row", () => {
		cy.window().then((win) => {
			arm(win, { rows: [row({ [DAY]: 12 })] });
		});
		clickSubmit();
		cy.window().then((win) => {
			const text = win.__("{0} cannot be more than {1} hours.", [DATE, 8]);
			expectDialog(text);
			expectCell("ut_day_totals", DAY, text);
		});
	});

	it("shows the blocking planned-hours limit", () => {
		cy.window().then((win) => {
			limitsReply = () => ({
				statusCode: 200,
				body: {
					message: [
						{
							status: "block",
							planned_hours: 10,
							limit: 100,
							total_hours: 12,
							task_subject: "Subject",
							role: "Developer",
						},
					],
				},
			});
			arm(win, { rows: [row()] });
		});
		clickSubmit();
		cy.window().then((win) => {
			expectDialog(
				win.__(
					'Work efforts for task "{0}" (role: {1}) exceeded the blocking limit ({2} h.) by {3} hour(s).',
					["Subject", "Developer", 10, 2]
				)
			);
		});
	});

	it("shows missing mandatory planned hours", () => {
		cy.window().then((win) => {
			limitsReply = () => ({
				statusCode: 200,
				body: {
					message: [
						{
							status: "block",
							planned_hours: 0,
							task_subject: "Subject",
							role: "Developer",
						},
					],
				},
			});
			arm(win, { rows: [row()] });
		});
		clickSubmit();
		cy.window().then((win) => {
			expectDialog(
				win.__(
					'Mandatory planned work efforts are not defined for task "{0}" (role: {1})',
					["Subject", "Developer"]
				)
			);
		});
	});

	it("shows a limits API failure", () => {
		cy.window().then((win) => {
			limitsReply = () => ({
				statusCode: 500,
				body: { exc_type: "ValidationError", exception: "limits down" },
			});
			arm(win, { rows: [row()] });
		});
		clickSubmit();
		cy.window().then((win) => {
			expectDialog(win.__("Error checking planned work efforts and limits"));
		});
	});
});
