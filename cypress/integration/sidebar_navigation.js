Cypress.removeAllListeners("uncaught:exception");
Cypress.on("uncaught:exception", (error) => {
	if (error.message.includes("ResizeObserver loop completed with undelivered notifications."))
		return false;
});
const httpErrors = [];
Cypress.on("fail", (error) => {
	if (httpErrors.length)
		error.message += "\nSafe HTTP diagnostics: " + JSON.stringify(httpErrors);
	throw error;
});
beforeEach(() => {
	cy.intercept("**/api/**", (req) => {
		req.on("response", (res) => {
			if (res.statusCode >= 400)
				httpErrors.push({
					url: req.url.split("?")[0],
					status: res.statusCode,
					exception: String(res.body?.exception || "").slice(0, 500),
				});
		});
	});
});

const helper = "dinext_timesheets.tests.sidebar_navigation_ui";
let fixture;

function assertRail(kind) {
	cy.window({ timeout: 60000 }).should((win) => {
		expect(
			win.frappe.boot.dinext_workspace_sidebar_hover_expand,
			"real site navigation setting"
		).to.eq(true);
		const route = win.frappe.get_route();
		if (kind === "list" || kind === "form") {
			expect(
				win.document.body.classList.contains("ut-hide-desk-sidebar"),
				"timesheet handler applied"
			).to.eq(true);
			const stylesheetLoaded = [...win.document.styleSheets].some((sheet) => {
				try {
					return [...sheet.cssRules].some((rule) =>
						rule.selectorText?.includes("body.ut-hide-desk-sidebar")
					);
				} catch {
					return false;
				}
			});
			expect(stylesheetLoaded, "timesheet layout stylesheet loaded").to.eq(true);
		}
		if (kind === "workspace" || kind === "positions") {
			expect(win.document.body.classList.contains("ut-hide-desk-sidebar")).to.eq(false);
		}
		if (kind === "workspace") {
			expect(route[0]).to.eq("Workspaces");
			expect(win.frappe.workspace?._page?.name, "workspace page initialized").to.exist;
		} else if (kind === "form") {
			expect(route.slice(0, 2)).to.deep.eq(["Form", "User Timesheet"]);
			expect(win.cur_frm?.doc?.name).to.eq(fixture.timesheet);
		} else {
			const doctype = kind === "list" ? "User Timesheet" : "User Timesheet Position";
			expect(route.slice(0, 2)).to.deep.eq(["List", doctype]);
			expect(win.cur_list?.doctype).to.eq(doctype);
			expect(win.cur_list?.$frappe_list?.length).to.eq(1);
		}
	});
	cy.window().then((win) => {
		const wrapper =
			kind === "workspace"
				? win.frappe.workspace.page.wrapper
				: kind === "form"
				? win.cur_frm.page.wrapper
				: win.cur_list.page.wrapper;
		cy.wrap(wrapper).as("navPage");
	});
	cy.get("@navPage")
		.should("be.visible")
		.find(".dinext-ws-rail-section")
		.as("navRail")
		.should("be.visible");
	if (kind === "positions") {
		cy.get("@navPage")
			.find(".layout-side-section:not(.dinext-ws-rail-section)")
			.should("not.be.visible");
	}
	cy.get("@navRail").find(".desk-sidebar").should("be.visible");
	cy.get("@navRail")
		.find("a.item-anchor[href^='/app/']")
		.filter(":visible")
		.first()
		.should("be.visible");
}

function destinations() {
	return [
		["list", `/app/user-timesheet?name=${encodeURIComponent(fixture.timesheet)}`],
		[
			"positions",
			`/app/user-timesheet-position?user_timesheet=${encodeURIComponent(fixture.timesheet)}`,
		],
		["form", `/app/user-timesheet/${encodeURIComponent(fixture.timesheet)}`],
	];
}

context("Timesheet site navigation", { defaultCommandTimeout: 30000 }, () => {
	before(() => {
		cy.login();
		cy.openDesk("/app");
		cy.call(`${helper}.seed_sidebar_navigation`, {}, { timeout: 180000 }).then((res) => {
			fixture = res.body.message;
		});
	});
	after(() => {
		cy.login();
		cy.openDesk("/app");
		cy.call(`${helper}.cleanup_sidebar_navigation`, {}, { timeout: 180000 });
	});

	it("keeps the global rail on direct entry to both lists and the saved form", () => {
		cy.login(fixture.user, fixture.password);
		for (const [name, path] of destinations()) {
			cy.openDesk(path);
			assertRail(name);
			cy.screenshot(`sidebar-direct-${name}`, { capture: "viewport" });
		}
	});

	it("retains hover navigation through refresh, SPA routes and both runtime themes", () => {
		cy.login(fixture.user, fixture.password);
		cy.openDesk("/app");
		assertRail("workspace");
		cy.window().then((win) => win.frappe.after_ajax());
		for (const theme of ["light", "dark"]) {
			cy.window().then((win) => win.frappe.ui.set_theme(theme));
			for (const [name, path] of destinations()) {
				cy.window().then((win) => {
					if (name === "form")
						return win.frappe.set_route("Form", "User Timesheet", fixture.timesheet);
					win.frappe.route_options =
						name === "list"
							? { name: fixture.timesheet }
							: { user_timesheet: fixture.timesheet };
					return win.frappe.set_route(
						"List",
						name === "list" ? "User Timesheet" : "User Timesheet Position",
						"List"
					);
				});
				assertRail(name);
				cy.window().then((win) =>
					name === "form" ? win.cur_frm.refresh() : win.cur_list.refresh()
				);
				assertRail(name);
				let width;
				cy.get("@navPage")
					.find(".layout-main-section-wrapper")
					.first()
					.then(($main) => {
						width = $main[0].getBoundingClientRect().width;
					});
				cy.get("@navRail").should(($rail) => {
					expect($rail.data("dinext-ws-hover")).to.eq(1);
				});
				cy.get("@navRail").trigger("mouseout").trigger("mouseover");
				cy.get("body").should("have.class", "dinext-ws-sidebar-hover-open");
				cy.get("@navRail")
					.find(".sidebar-item-label")
					.filter(":visible")
					.first()
					.should("be.visible");
				cy.get("@navPage")
					.find(".layout-main-section-wrapper")
					.first()
					.should(($main) => {
						expect(
							Math.abs($main[0].getBoundingClientRect().width - width)
						).to.be.lessThan(2);
					});
				cy.screenshot(`sidebar-${theme}-${name}`, { capture: "viewport" });
				cy.get("@navRail")
					.find("a.item-anchor[href^='/app/']")
					.filter(":visible")
					.first()
					.click();
				cy.window().should((win) => expect(win.frappe.get_route()[0]).to.eq("Workspaces"));
				assertRail("workspace");
			}
		}
	});
});
