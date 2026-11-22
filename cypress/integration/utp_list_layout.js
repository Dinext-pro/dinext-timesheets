Cypress.removeAllListeners("uncaught:exception");

const source = "User Timesheet Position";
const helper = "dinext_timesheets.tests.utp_list_ui";
const queueApi = "dinext_common.workflow_approval.api.get_my_queue";
const root = ".dinext-utp-list:visible";
const actionMenu = ".page-container:visible .actions-btn-group";
const availabilityApi = "dinext_common.workflow_approval.api.get_common_list_transitions";
const bulkApi = "frappe.model.workflow.bulk_workflow_approval";
const voteApi = "dinext_common.workflow_approval.api.bulk_vote";
const jobApi = "dinext_common.workflow_approval.api.get_bulk_workflow_job";
const approve = "_Cypress UTP List Approve";
const fields = ["user", "period", "project", "project_role", "document_name", "all_hours"];
let fixture;

function openList(user = fixture.approver, rowCount = 20) {
	cy.login(user, fixture.password);
	cy.openDesk(
		`/app/user-timesheet-position?user_timesheet=${encodeURIComponent(fixture.timesheet)}`
	);
	// Cold Desk metadata can still be loading after the page itself is ready.
	cy.window({ timeout: 60000 }).should((win) => {
		expect(win.cur_list?.doctype).to.eq(source);
		expect(win.cur_list.data.length).to.be.greaterThan(0);
		expect(win.cur_list.data.every((row) => row.user_timesheet === fixture.timesheet)).to.eq(
			true
		);
	});
	cy.get(`${root} .list-row .dinext-utp-actions`).should("have.length", rowCount);
}

function requestArgs(body) {
	return typeof body === "string" ? Object.fromEntries(new URLSearchParams(body)) : body;
}

function requestNames(value) {
	return typeof value === "string" ? JSON.parse(value) : value;
}

function spyOnNotifications() {
	cy.window().then((win) => {
		cy.spy(win.frappe, "show_alert").as("alert");
		cy.spy(win.frappe, "show_progress").as("progress");
	});
}

function availableRowCheckboxes() {
	return cy.get(`${root} .list-row:has(.dinext-utp-action-select) .list-row-checkbox`);
}

function selectVisibleRows(count) {
	cy.get(`${root} .btn-more`).click();
	availableRowCheckboxes().should("have.length", count).then(($boxes) => {
		cy.wrap($boxes.slice(0, count)).check({ force: true });
	});
	cy.get(`${actionMenu} > button`).click();
	cy.contains(`${actionMenu} .dinext-list-workflow-item a`, approve).click();
}

function assertUnlocked() {
	cy.window().should((win) => {
		const wrapper = win.cur_list.page.wrapper[0];
		expect(wrapper.inert).to.eq(false);
		expect(wrapper.hasAttribute("aria-busy")).to.eq(false);
	});
}

function assertHeaders() {
	cy.get(`${root} .list-row-head .list-row-col span[data-sort-by]`).should(($headers) => {
		expect(
			[...$headers]
				.filter((el) => el.getBoundingClientRect().width > 0)
				.map((el) => el.dataset.sortBy)
		).to.deep.eq(fields);
	});
}

function assertGeometry() {
	cy.get(`${root} .list-row`, { timeout: 10000 }).should(($rows) => {
		const errors = [];
		const check = (valid, label) => {
			if (!valid) errors.push(label);
		};
		for (const row of $rows) {
			const rect = row.getBoundingClientRect();
			const groups = row.querySelectorAll(".dinext-utp-actions");
			check(groups.length === 1, "one controls group");
			if (!groups.length) continue;
			const controls = [...groups[0].children];
			check(controls.length === 4, "one state and three utilities");
			check(Math.abs(rect.height - 40) < 1, `row height ${rect.height}`);
			const center = rect.top + rect.height / 2;
			for (const control of controls) {
				const box = control.getBoundingClientRect();
				check(
					Math.abs(box.top + box.height / 2 - center) <= 1,
					`center offset ${box.top + box.height / 2 - center}`
				);
				check(
					box.top >= rect.top - 1 && box.bottom <= rect.bottom + 1,
					"vertical overflow"
				);
				check(box.right <= rect.right + 1, "horizontal overflow");
			}
			for (const button of groups[0].querySelectorAll("button")) {
				check(
					Math.abs(button.getBoundingClientRect().width - 24) < 1,
					`button width ${button.getBoundingClientRect().width}`
				);
				check(
					Math.abs(button.getBoundingClientRect().height - 24) < 1,
					`button height ${button.getBoundingClientRect().height}`
				);
			}
			check(
				groups[0].firstElementChild.matches("select, .indicator-pill"),
				"state control comes first"
			);
		}
		expect(errors.slice(0, 10), "compact aligned controls").to.deep.eq([]);
	});
}

context("Productive timesheet position List View", () => {
	before(() => {
		cy.login();
		cy.openDesk("/app");
		cy.call(`${helper}.seed_utp_list`, {}, { timeout: 180000 }).then((res) => {
			fixture = res.body.message;
		});
	});
	after(() => {
		cy.login();
		cy.openDesk("/app");
		cy.call(`${helper}.cleanup_utp_list`, {}, { timeout: 180000 });
	});
	beforeEach(() => cy.viewport(1920, 1080));

	it("shows the six productive default columns and their values in a fresh session", () => {
		openList();
		assertHeaders();
		cy.window({ timeout: 20000 }).should((win) => {
			const first = win.cur_list.data[0];
			const cells = win.cur_list.$frappe_list
				.find(`a[data-name="${first.name}"]`)
				.closest(".list-row")
				.find(".level-left .list-row-col:visible");
			expect(cells.length).to.eq(6);
			expect(cells.eq(0).text()).to.contain(fixture.owner_name);
			expect(cells.eq(1).text()).to.contain(fixture.period);
			expect(cells.eq(2).text()).to.contain("Cypress");
			expect(cells.eq(3).text()).to.contain(fixture.project_role);
			expect(cells.eq(4).text()).to.contain("Cypress List Document");
			expect(cells.eq(5).text()).to.contain(String(first.all_hours));
		});
		cy.screenshot("utp-list-production-columns", { capture: "viewport", scale: true });
	});

	it("shows one personal menu before the utilities and keeps it inside the row", () => {
		openList();
		cy.call(queueApi, {}).then((res) => {
			expect(
				res.body.message.filter((task) =>
					fixture.positions.some((position) => position.name === task.reference_name)
				)
			).to.have.length(20);
		});
		cy.get(`${root} .dinext-utp-actions .indicator-pill`).should("not.exist");
		cy.get(`${root} .dinext-utp-action-select`).should("have.length", 20);
		cy.get(`${root} .dinext-utp-action-select`)
			.first()
			.should(($select) => {
				const style = $select[0].ownerDocument.defaultView.getComputedStyle($select[0]);
				expect(style.appearance, "visible native dropdown affordance").not.to.eq("none");
				expect(style.textAlignLast).to.eq("center");
			});
		assertGeometry();
	});

	it("keeps the toolbar compact after selection, refresh and theme changes", () => {
		openList();
		const assertNoExtraAction = () =>
			cy
				.contains(
					".page-container:visible .inner-toolbar button",
					/Apply workflow action|Применить действие согласования/
				)
				.should("not.exist");
		assertNoExtraAction();
		cy.get(`${root} .list-row-checkbox`).first().check({ force: true });
		cy.get(".page-container:visible .actions-btn-group > button").should("be.visible").click();
		cy.get(".page-container:visible .actions-btn-group .dropdown-menu").should("be.visible");
		assertNoExtraAction();
		cy.get(".page-container:visible .actions-btn-group > button").click();
		for (const theme of ["light", "dark"]) {
			cy.window().then((win) => win.frappe.ui.set_theme(theme));
			cy.window().then((win) => win.cur_list.refresh());
			cy.get(`${root} .dinext-utp-action-select`).should("have.length", 20);
			assertNoExtraAction();
		}
	});

	it("shows only a status indicator when the viewer has no personal transitions", () => {
		openList(fixture.viewer, 1);
		cy.get(`${root} .dinext-utp-action-select`).should("not.exist");
		cy.get(`${root} .dinext-utp-actions .indicator-pill`).should("have.length", 1);
		assertGeometry();
	});

	it("retains columns and normal filters through refresh, paging and reopening", () => {
		openList();
		cy.get(`${root} .btn-more`).click();
		cy.get(`${root} .list-row .dinext-utp-actions`).should("have.length", 21);
		cy.window().then((win) => win.cur_list.filter_area.add(source, "all_hours", ">", 10));
		cy.window({ timeout: 20000 }).should((win) => {
			expect(win.cur_list.data).to.have.length(11);
			expect(win.cur_list.data.every((row) => row.all_hours > 10)).to.eq(true);
		});
		cy.get(`${root} span[data-sort-by="all_hours"]`).click();
		cy.window().then((win) => win.cur_list.refresh());
		cy.get(`${root} .list-row .dinext-utp-actions`).should("have.length", 11);
		assertHeaders();
		assertGeometry();
		cy.reload();
		cy.window({ timeout: 20000 }).should((win) => {
			expect(win.cur_list?.data).to.have.length(11);
			expect(
				win.cur_list.data.every(
					(row) => row.user_timesheet === fixture.timesheet && row.all_hours > 10
				)
			).to.eq(true);
		});
		assertHeaders();
		assertGeometry();
		cy.window().then((win) => win.cur_list.filter_area.remove("all_hours"));
		cy.get(`${root} .list-row .dinext-utp-actions`).should("have.length", 20);
	});

	it("aligns headers and controls in both themes and scrolls only the narrow list", () => {
		openList();
		for (const theme of ["light", "dark"]) {
			cy.window().then((win) => win.frappe.ui.set_theme(theme));
			for (const width of [1920, 1280, 1024, 360]) {
				cy.viewport(width, 900);
				assertHeaders();
				assertGeometry();
				cy.document({ timeout: 10000 }).should((doc) => {
					expect(
						doc.documentElement.scrollWidth,
						"horizontal overflow stays inside list"
					).to.be.at.most(doc.documentElement.clientWidth + 1);
				});
				cy.get(root).should(($list) => {
					if (width === 360)
						expect($list[0].scrollWidth).to.be.greaterThan($list[0].clientWidth);
					const header = $list.find(".list-row-head > .level-left").first()[0];
					const row = $list.find(".list-row > .level-left").first()[0];
					expect(
						Math.abs(
							header.getBoundingClientRect().left - row.getBoundingClientRect().left
						)
					).to.be.at.most(1);
					expect(
						Math.abs(
							header.getBoundingClientRect().width -
								row.getBoundingClientRect().width
						)
					).to.be.at.most(1);
				});
			}
			cy.viewport(1920, 1080);
			cy.screenshot(`utp-list-${theme}`, { capture: "viewport", scale: true });
		}
	});

	it("keeps compact list styles out of the timesheet list and form", () => {
		openList();
		cy.window().then((win) => win.frappe.set_route("List", "User Timesheet", "List"));
		cy.window({ timeout: 20000 }).should((win) => {
			expect(win.cur_list?.doctype).to.eq("User Timesheet");
			expect(win.cur_list.$frappe_list.hasClass("dinext-utp-list")).to.eq(false);
		});
		cy.window().then((win) =>
			win.frappe.set_route("Form", "User Timesheet", fixture.timesheet)
		);
		cy.window().should((win) => expect(win.cur_frm?.doc?.name).to.eq(fixture.timesheet));
		cy.get(".dinext-utp-list:visible").should("not.exist");
		cy.get(".dinext-utp-actions:visible").should("not.exist");
	});

	it("loads workflow actions for exactly the checked rows and shows batch progress after clicking", () => {
		let selected;
		let releaseLookup;
		let releaseVote;
		const lookupGate = new Promise((resolve) => {
			releaseLookup = resolve;
		});
		const voteGate = new Promise((resolve) => {
			releaseVote = resolve;
		});
		cy.intercept("POST", `**/api/method/${availabilityApi}`, (req) => {
			req.continue(() => lookupGate);
		}).as("available");
		cy.intercept("POST", `**/api/method/${bulkApi}`, async (req) => {
			const names = requestNames(requestArgs(req.body).docnames);
			await voteGate;
			req.reply({
				body: { message: { succeeded: names.map((name) => ({ name })), failed: [] } },
			});
		}).as("bulk");
		openList();
		spyOnNotifications();
		availableRowCheckboxes().then(($boxes) => {
			const checked = $boxes.toArray().slice(0, 2);
			selected = checked.map((box) => box.dataset.name);
			checked.forEach((box) => cy.wrap(box).check({ force: true }));
		});
		cy.get(`${actionMenu} > button`).click();
		cy.get(`${actionMenu} .dinext-workflow-menu-status`).should("be.visible");
		cy.get(`${actionMenu} .dinext-list-workflow-item`).should("not.exist");
		cy.then(releaseLookup);
		cy.wait("@available").then(({ request }) => {
			expect(requestNames(requestArgs(request.body).names)).to.have.members(selected);
		});
		cy.get(`${actionMenu} .dinext-list-workflow-item`)
			.should("have.length", 1)
			.find(".dinext-workflow-transition")
			.should("have.attr", "data-workflow-style");
		cy.contains(`${actionMenu} .dinext-list-workflow-item a`, approve).click();
		cy.get(".modal:visible [data-fieldname='comment']").should("not.exist");
		cy.get(".modal:visible .progress").should("be.visible");
		cy.window().should((win) => {
			expect(win.cur_list.page.wrapper[0].inert).to.eq(true);
		});
		cy.get("@progress").should("have.been.calledWith", Cypress.sinon.match.string, 0, 2);
		cy.then(releaseVote);
		cy.wait("@bulk").then(({ request }) => {
			const args = requestArgs(request.body);
			expect(requestNames(args.docnames)).to.have.members(selected);
			expect(args.doctype).to.eq(source);
			expect(args.action).to.eq(approve);
			expect(args.transition_uuid).to.eq("cypress-utp-list-approve");
			expect(args.comment).to.eq("");
			expect(args.request_id).to.be.a("string").and.not.be.empty;
		});
		cy.get("@progress").should("have.been.calledWith", Cypress.sinon.match.string, 2, 2);
		cy.get(".modal:visible .progress-bar").should("not.exist");
		cy.get(".modal:visible, #freeze, .modal-backdrop").should("not.exist");
		cy.get("@alert").should("not.have.been.called");
		assertUnlocked();
	});

	it("finishes a successful background batch quietly after closing progress", () => {
		const jobId = "ef".repeat(16);
		let names;
		cy.intercept("POST", `**/api/method/${bulkApi}`, (req) => {
			names = requestNames(requestArgs(req.body).docnames);
			req.reply({ body: { message: { job_id: jobId } } });
		}).as("queuedSuccess");
		cy.intercept("POST", `**/api/method/${jobApi}`, (req) => {
			req.reply({ body: { message: {
				status: "finished",
				result: { succeeded: names.map((name) => ({ name })), failed: [] },
			} } });
		}).as("successfulJob");
		openList();
		spyOnNotifications();
		selectVisibleRows(20);
		cy.wait("@queuedSuccess");
		cy.wait("@successfulJob");
		cy.get("@progress").should("have.been.calledWith", Cypress.sinon.match.string, 0, 20);
		cy.get("@progress").should("have.been.calledWith", Cypress.sinon.match.string, 20, 20);
		cy.get(".modal:visible, #freeze, .modal-backdrop").should("not.exist");
		cy.get("@alert").should("not.have.been.called");
		assertUnlocked();
	});

	it("keeps a background batch locked until its result and shows partial failures", () => {
		const jobId = "ab".repeat(16);
		let names;
		let polls = 0;
		let finishJob;
		const waitForResult = new Promise((resolve) => {
			finishJob = resolve;
		});
		cy.intercept("POST", `**/api/method/${bulkApi}`, (req) => {
			names = requestNames(requestArgs(req.body).docnames);
			req.reply({ body: { message: { job_id: jobId } } });
		}).as("queuedBatch");
		cy.intercept("POST", `**/api/method/${jobApi}`, async (req) => {
			expect(requestArgs(req.body).job_id).to.eq(jobId);
			polls += 1;
			if (polls === 1) {
				req.reply({ body: { message: { status: "pending" } } });
				return;
			}
			await waitForResult;
			req.reply({
				body: {
					message: {
						status: "finished",
						result: {
							succeeded: names.slice(1).map((name) => ({ name })),
							failed: [{ name: names[0], error: "Task already completed" }],
						},
					},
				},
			});
		}).as("batchStatus");
		openList();
		spyOnNotifications();
		selectVisibleRows(20);
		cy.wait("@queuedBatch").then(() => expect(names).to.have.length(20));
		cy.wait("@batchStatus");
		cy.get(".modal:visible .progress").should("be.visible");
		cy.window().should((win) => expect(win.cur_list.page.wrapper[0].inert).to.eq(true));
		cy.then(finishJob);
		cy.wait("@batchStatus");
		cy.get("@progress").should("have.been.calledWith", Cypress.sinon.match.string, 20, 20);
		cy.contains(".modal:visible", "Task already completed").should("be.visible");
		assertUnlocked();
	});

	it("unlocks a background batch with an unconfirmed result if the status request fails", () => {
		cy.intercept("POST", `**/api/method/${bulkApi}`, {
			body: { message: { job_id: "cd".repeat(16) } },
		}).as("queuedBatch");
		cy.intercept("POST", `**/api/method/${jobApi}`, { forceNetworkError: true }).as("lostStatus");
		openList();
		selectVisibleRows(20);
		cy.wait("@queuedBatch");
		cy.wait("@lostStatus");
		cy.contains(".modal:visible", "The workflow result could not be confirmed").should("be.visible");
		cy.get(".modal:visible .progress").should("not.exist");
		assertUnlocked();
		cy.get("@queuedBatch.all").should("have.length", 1);
	});

	it("runs a single row approval without a comment dialog or success notification", () => {
		let name;
		cy.intercept("POST", `**/api/method/${voteApi}`, (req) => {
			const names = requestNames(requestArgs(req.body).names);
			req.reply({ body: { message: { succeeded: names.map((name) => ({ name })), failed: [] } } });
		}).as("vote");
		openList();
		spyOnNotifications();
		cy.get(`${root} .dinext-utp-action-select`).first().then(($select) => {
			name = $select.closest(".list-row").find(".list-row-checkbox")[0].dataset.name;
			cy.wrap($select).select(approve);
		});
		cy.wait("@vote").then(({ request }) => {
			const args = requestArgs(request.body);
			expect(requestNames(args.names)).to.deep.eq([name]);
			expect(args.action).to.eq(approve);
			expect(args.comment).to.eq("");
		});
		assertUnlocked();
		cy.get(".modal:visible").should("not.exist");
		cy.get("@alert").should("not.have.been.called");
		cy.get("@progress").should("not.have.been.called");
	});

	it("cancels a required comment safely and unlocks the row after a failed vote", () => {
		const error = "The selected workflow item is no longer available";
		const reject = "Reject";
		cy.intercept("POST", `**/api/method/${queueApi}`, (req) => {
			req.continue((res) => {
				for (const task of res.body.message) {
					if (fixture.positions.some((position) => position.name === task.reference_name)) {
						task.available_transitions[0].action = reject;
						task.available_transitions[0].next_state = "Rejected";
						task.available_transitions[0].comment_is_required = true;
					}
				}
			});
		});
		cy.intercept("POST", `**/api/method/${voteApi}`, (req) => {
			const [name] = requestNames(requestArgs(req.body).names);
			req.reply({ body: { message: { succeeded: [], failed: [{ name, error }] } } });
		}).as("failedVote");
		openList();
		const selects = `${root} .dinext-utp-action-select`;
		cy.get(selects).first().select(reject);
		cy.window().should((win) => expect(win.cur_dialog?.display).to.eq(true));
		cy.get(".modal:visible .modal-header button.btn-modal-close").click();
		cy.get(".modal:visible").should("not.exist");
		cy.get("@failedVote.all").should("have.length", 0);
		assertUnlocked();
		cy.get(selects).first().should("have.value", "").select(reject);
		cy.get(".modal:visible textarea[data-fieldname='comment']").type("Please review the hours").blur();
		cy.get(".modal:visible .modal-footer .btn-primary").click();
		cy.wait("@failedVote", { requestTimeout: 15000 }).then(({ request }) => {
			expect(requestArgs(request.body).action).to.eq(reject);
			expect(requestArgs(request.body).comment).to.eq("Please review the hours");
		});
		cy.contains(".modal:visible", error).should("be.visible");
		assertUnlocked();
		cy.get(selects).first().should("have.value", "").and("be.enabled");
	});
});
