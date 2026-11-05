Cypress.removeAllListeners("uncaught:exception");
Cypress.on("uncaught:exception", (error) => {
	// Chromium can defer resize notifications while Frappe renders a list.
	// Keep every other application exception fatal to the test.
	if (error.message === "ResizeObserver loop completed with undelivered notifications.") {
		Cypress.log({ name: "ResizeObserver", message: error.message });
		return false;
	}
});
const helper = "dinext_timesheets.tests.my_timesheets_cards_ui";
const workspace = "/app/my-timesheets";
const legacyWorkspace = `/app/${encodeURIComponent("мои-таймшиты")}`;
const cases = [
	["Моих Таймшитов всего", "таймшитов всего", "My Timesheets"],
	["Моих таймшитов на редактировании", "тш на редактировании", "My Timesheets"],
	["Моих таймшитов на согласовании", "тш на согласовании", "My Timesheets"],
	["Мои отклоненные таймшиты", "тш отклонено", "My Timesheets"],
	["Мои просроченные таймшиты", "тш просрочено", "My Timesheets"],
	["Мои согласованные таймшиты", "тш согласовано", "My Timesheets"],
	["Всего заявок на расходы", "Всего заявок на расходы", "Мои Заявки на расходы"],
	["Заявок EC на согласовании", "из них на согласовании", "Мои Заявки на расходы"],
	["Заявок EC Согласовано", "из них согласовано", "Мои Заявки на расходы"],
	["Заявок EC Отклонено", "из них отклонено", "Мои Заявки на расходы"],
	["Моих Заявок всего", "заявок всего", "Мои Заявки на отсутствие"],
	["Моих Заявок на согласовании", "заявок на согласовании", "Мои Заявки на отсутствие"],
	["Моих Заявок Согласовано", "заявок согласовано", "Мои Заявки на отсутствие"],
	["Моих Заявок Отклонено", "заявок отклонено", "Мои Заявки на отсутствие"],
	["ТШ у меня на согласовании-2", "ТШ у меня на согласовании", "По Таймшитам"],
	["ТШ согласованные мной-1", "ТШ согласованные мной", "По Таймшитам"],
	[
		"Заявки на отсутствие у меня на согласовании-2",
		"Заявки у меня на согласовании",
		"По Заявкам на отсутствие",
	],
	[
		"Заявки на отсутствие согласованные мной-1",
		"Заявки согласованные мной",
		"По Заявкам на отсутствие",
	],
	[
		"Заявок EC у меня на согласовании",
		"Расходы у меня на согласовании",
		"По Заявкам на расходы",
	],
	["Заявок EC Согласованных мной", "Расходы согласованные мной", "По Заявкам на расходы"],
];
let fixture;

function open(user, route = workspace) {
	cy.login(user || fixture.user, fixture.password);
	cy.openDesk(route);
	cy.get(".number-widget-box", { timeout: 60000 }).should("have.length", cases.length);
}

function cardWidget(label) {
	return cy
		.get(".number-widget-box")
		.filter((_, el) =>
			[...el.querySelectorAll(".widget-title")].some(
				(title) => title.textContent.trim() === label
			)
		)
		.should("have.length", 1);
}

function sectionFor(name) {
	const names = new Map(fixture.workspace_cards.map((row) => [row.label, row.name]));
	let section = "";
	let column = 0;
	const approvalHeaders = [];
	const sections = {
		"My Timesheets": "My Timesheets",
		"My Expense Claims": "Мои Заявки на расходы",
		"My Leave Applications": "Мои Заявки на отсутствие",
	};
	const approvalSections = {
		"Timesheet Approvals": "По Таймшитам",
		"Leave Approvals": "По Заявкам на отсутствие",
		"Expense Approvals": "По Заявкам на расходы",
	};
	for (const block of fixture.workspace_content) {
		if (block.type === "header") {
			const text = block.data.text.replace(/<[^>]*>/g, "").trim();
			if (sections[text]) section = sections[text];
			if (text === "My Approvals") section = "approvals";
			if (section === "approvals" && approvalSections[text]) {
				approvalHeaders.push(approvalSections[text]);
			}
		}
		if (block.type === "number_card") {
			const current = section === "approvals" ? approvalHeaders[column++ % 3] : section;
			if (names.get(block.data.number_card_name) === name) {
				if (section === "approvals") expect(block.data.col).to.eq(4);
				return current;
			}
		}
	}
	throw new Error(`Card missing from workspace content: ${name}`);
}

function readPages(doctype, filters, expected, start = 0, gathered = []) {
	cy.call("frappe.desk.reportview.get", {
		doctype,
		fields: ["name"],
		filters,
		order_by: "name asc",
		start,
		page_length: 5,
	}).then((res) => {
		const message = res.body.message;
		const rows = Array.isArray(message) ? message : message.values || [];
		gathered.push(...rows.map((row) => (Array.isArray(row) ? row[0] : row.name)));
		if (rows.length === 5) readPages(doctype, filters, expected, start + 5, gathered);
		else expect(gathered).to.have.members(expected);
	});
}

describe("My Timesheets: 20 section-aware Number Cards", () => {
	before(() => {
		cy.task("numberCardsSeed", null, { timeout: 180000 }).then((data) => {
			fixture = data;
			expect(Object.keys(fixture.expected)).to.have.length(cases.length);
		});
	});
	afterEach(function () {
		if (this.currentTest.err)
			cy.window().then((win) =>
				cy.writeFile("cypress/results/number-cards-failure.json", {
					title: this.currentTest.title,
					message: this.currentTest.err.message,
					routeOptions: win.frappe?.route_options,
					filters: win.cur_list?.filter_area?.get(),
					lastArgs: win.cur_list?.last_args,
					route: win.location.href,
				})
			);
	});
	after(() => {
		cy.task("numberCardsCleanup", null, { timeout: 180000 });
	});

	for (const [name, label, section] of cases.filter(
		(_, index) =>
			Cypress.env("numberCardIndex") === undefined ||
			index === Number(Cypress.env("numberCardIndex"))
	)) {
		it(`${section}: ${label} matches its API and full drill-down`, () => {
			open();
			expect(sectionFor(name)).to.eq(section);
			cy.get(".layout-main-section").should("contain", section === "My Timesheets" ? "Мои Таймшиты" : section);
			cardWidget(label)
				.find(".number")
				.should("have.text", String(fixture.expected[name].length));
			cy.window().then((win) => {
				const doc = win.locals["Number Card"][name];
				const filters = win.frappe.dashboard_utils.get_all_filters(doc);
				const method =
					doc.type === "Custom"
						? doc.method
						: "frappe.desk.doctype.number_card.number_card.get_result";
				cy.call(method, doc.type === "Custom" ? { filters } : { doc, filters }).then(
					(res) => {
						const value =
							typeof res.body.message === "object"
								? res.body.message.value
								: res.body.message;
						expect(value).to.eq(fixture.expected[name].length);
					}
				);
				if (doc.type === "Document Type") {
					expect(doc.show_percentage_stats).to.eq(1);
					expect(doc.stats_time_interval).to.eq("Daily");
					cy.call(
						"frappe.desk.doctype.number_card.number_card.get_percentage_difference",
						{
							doc,
							filters,
							result: fixture.expected[name].length,
						}
					)
						.its("body.message")
						.should("eq", 0);
					cardWidget(label)
						.find(".percentage-stat-area")
						.should("contain.text", "0")
						.and("contain.text", "%");
				} else {
					cardWidget(label).find(".card-stats").should("not.exist");
				}
			});
			cardWidget(label).find(".widget-body").click();
			cy.window({ timeout: 60000 }).should((win) => {
				expect(win.cur_list?.doctype).to.be.a("string");
				expect(win.cur_list?.filter_area?.get).to.be.a("function");
				expect(win.cur_list?.data?.length).to.be.greaterThan(0);
				for (const row of win.cur_list.data)
					expect(fixture.expected[name]).to.include(row.name);
			});
			cy.window().then((win) => {
				const list = win.cur_list;
				const filters = list.filter_area.get();
				cy.call("frappe.desk.reportview.get_count", {
					doctype: list.doctype,
					filters,
				}).then((res) => {
					expect(res.body.message).to.eq(fixture.expected[name].length);
				});
				readPages(list.doctype, filters, fixture.expected[name]);
			});
		});
	}

	it("renders English captions and resolves the legacy route", () => {
		open(fixture.other, legacyWorkspace);
		cy.location("pathname").should("eq", workspace);
		cy.contains(".ce-header", "My Timesheets").should("be.visible");
		cy.contains(".ce-header", "My Expense Claims").should("be.visible");
		cardWidget("Total Expense Claims").should("be.visible");
	});

	(Cypress.env("numberCardIndex") === undefined ? it : it.skip)(
		"keeps every section and number readable in both themes and during a runtime switch",
		() => {
			open();
			for (const theme of ["light", "dark", "light"]) {
				cy.window().then((win) => win.frappe.ui.set_theme(theme));
				for (const [name, label] of cases) {
					cardWidget(label)
						.find(".number")
						.scrollIntoView()
						.should("be.visible")
						.and("have.text", String(fixture.expected[name].length));
				}
				cy.screenshot(`my-timesheets-cards-${theme}`, { capture: "fullPage" });
			}
		}
	);

	(Cypress.env("numberCardIndex") === undefined ? it : it.skip)(
		"aligns the two shortcut sections and opens Timesheet Settings",
		() => {
			open();
			cy.get(".layout-main-section .ce-block").then(($blocks) => {
				const blocks = [...$blocks];
				const heading = (text) =>
					blocks.findIndex(
						(block) => block.querySelector(".ce-header")?.textContent.trim() === text
					);
				const reportIndex = heading("Отчетность");
				const settingsIndex = heading("Настройки");
				expect(reportIndex).to.be.greaterThan(-1);
				expect(settingsIndex).to.be.greaterThan(reportIndex);

				const shortcuts = (rows) =>
					rows.flatMap((row) => [...row.querySelectorAll(".shortcut-widget-box")]);
				const reports = shortcuts(blocks.slice(reportIndex + 1, settingsIndex));
				const settings = shortcuts(blocks.slice(settingsIndex + 1));
				expect(reports.map((link) => link.getAttribute("aria-label"))).to.include.members([
					"Мои списания по ТШ",
					"Календарь отсутствий",
				]);
				const labels = settings.map((link) => link.getAttribute("aria-label"));
				const translate = blocks[0].ownerDocument.defaultView.__;
				for (const source of ["Worker", "Timesheet Template", "Timesheet Settings"]) {
					const caption = translate(source);
					expect(caption, source).to.match(/[А-Яа-яЁё]/);
					expect(labels).to.include(caption);
				}
				expect(settings[0].getBoundingClientRect().left).to.be.closeTo(
					reports[0].getBoundingClientRect().left,
					1
				);
			});
			cy.window().then((win) => {
				cy.contains(".shortcut-widget-box", win.__("Timesheet Settings")).click();
			});
			cy.window().should((win) => expect(win.cur_frm?.doctype).to.eq("Timesheet Settings"));
		}
	);

	(Cypress.env("numberCardIndex") === undefined ? it : it.skip)(
		"does not retain another user's data for a user without an Employee",
		() => {
			open(fixture.empty);
			cy.window().its("frappe.boot.dinext_expense_claim_employees").should("deep.eq", []);
			cy.get(".number-widget-box .number")
				.should("have.length", cases.length)
				.each(($number) => {
					expect($number.text()).to.eq("0");
				});
			cardWidget("Всего заявок на расходы").find(".widget-body").click();
			cy.window().should((win) => {
				expect(win.cur_list?.doctype).to.eq("Expense Claim");
				expect(win.cur_list.data).to.have.length(0);
			});
			open();
			cardWidget("ТШ у меня на согласовании").find(".number").should("have.text", "22");
		}
	);

	(Cypress.env("numberCardIndex") === undefined ? it : it.skip)(
		"refreshes reopened approvals and keeps a zero custom drill-down empty",
		() => {
			open();
			cardWidget("Заявки согласованные мной").find(".number").should("have.text", "1");
			cy.task("numberCardsReopen").then((data) => {
				fixture.expected = data.expected;
			});
			cy.reload();
			cardWidget("Заявки согласованные мной").find(".number").should("have.text", "0");
			cardWidget("Заявки согласованные мной").find(".widget-body").click();
			cy.window({ timeout: 60000 }).should((win) => {
				expect(win.cur_list?.doctype).to.eq("Application For Leave");
				expect(win.cur_list?.filter_area?.get()).to.deep.include([
					"Application For Leave",
					"name",
					"is",
					"not set",
					false,
				]);
			});
			cy.window().then((win) => {
				cy.call("frappe.desk.reportview.get_count", {
					doctype: win.cur_list.doctype,
					filters: win.cur_list.filter_area.get(),
				})
					.its("body.message")
					.should("eq", 0);
			});
		}
	);
});
