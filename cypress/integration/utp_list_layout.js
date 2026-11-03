Cypress.removeAllListeners("uncaught:exception");

const source = "User Timesheet Position";
const helper = "dinext_timesheets.tests.utp_list_ui";
const queueApi = "dinext_common.workflow_approval.api.get_my_queue";
const root = ".dinext-utp-list:visible";
const fields = ["user", "period", "project", "project_role", "document_name", "all_hours"];
let fixture;

function openList(user = fixture.approver) {
	cy.login(user, fixture.password);
	cy.openDesk(
		`/app/user-timesheet-position?user_timesheet=${encodeURIComponent(fixture.timesheet)}`
	);
	cy.window({ timeout: 20000 }).should((win) => {
		expect(win.cur_list?.doctype).to.eq(source);
		expect(win.cur_list.data.length).to.be.greaterThan(0);
		expect(win.cur_list.data.every((row) => row.user_timesheet === fixture.timesheet)).to.eq(
			true
		);
	});
	cy.get(`${root} .list-row .dinext-utp-actions`).should("have.length", 20);
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
			).to.have.length(21);
		});
		cy.get(`${root} .dinext-utp-actions .indicator-pill`).should("not.exist");
		cy.get(`${root} .dinext-utp-action-select`).should("have.length", 20);
		assertGeometry();
	});

	it("shows only a status indicator when the viewer has no personal transitions", () => {
		openList(fixture.viewer);
		cy.get(`${root} .dinext-utp-action-select`).should("not.exist");
		cy.get(`${root} .dinext-utp-actions .indicator-pill`).should("have.length", 20);
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
});
