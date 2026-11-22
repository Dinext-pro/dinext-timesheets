Cypress.removeAllListeners("uncaught:exception");
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

Cypress.on("uncaught:exception", (error) => {
	if (error.message.includes("ResizeObserver loop completed with undelivered notifications."))
		return false;
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

context("Timesheet sidebar alignment", { defaultCommandTimeout: 30000 }, () => {
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
	it("aligns the rail to the same viewport position across timesheet screens", () => {
		cy.login(fixture.user, fixture.password);
		const measurements = [];
		const errors = [];
		cy.openDesk(destinations()[0][1]);
		assertRail("list");
		for (const fullWidth of Cypress.env("quickGeometry")
			? [Boolean(Cypress.env("fullWidth"))]
			: [false, true]) {
			cy.window().then((win) => {
				if (win.document.body.classList.contains("full-width") !== fullWidth)
					win.frappe.ui.toolbar.toggle_full_width();
			});
			for (const width of Cypress.env("quickGeometry") ? [1024] : [1440, 1024]) {
				cy.viewport(width, 900);
				for (const theme of Cypress.env("quickGeometry") ? ["light"] : ["light", "dark"]) {
					let baseline;
					for (const [kind, path] of destinations()) {
						cy.window().then((win) => {
							if (kind === "form")
								return win.frappe.set_route(
									"Form",
									"User Timesheet",
									fixture.timesheet
								);
							win.frappe.route_options =
								kind === "list"
									? { name: fixture.timesheet }
									: { user_timesheet: fixture.timesheet };
							return win.frappe.set_route(
								"List",
								kind === "list" ? "User Timesheet" : "User Timesheet Position",
								"List"
							);
						});
						assertRail(kind);
						cy.window().then((win) => win.frappe.ui.set_theme(theme));
						cy.get("@navRail").then(($rail) => {
							const rail = $rail[0].getBoundingClientRect();
							const icon = $rail
								.find("a.item-anchor[href^='/app/'] svg:visible")[0]
								.getBoundingClientRect();
							const main = $rail
								.closest(".layout-main")
								.find(".layout-main-section-wrapper")[0]
								.getBoundingClientRect();
							const point = {
								width,
								theme,
								kind,
								rail: rail.left,
								icon: icon.left,
								main: main.left,
								contentWidth: main.width,
							};
							const title = $rail
								.closest(".page-container")
								.find(".page-head .page-title")[0]
								.getBoundingClientRect();
							const card = $rail
								.closest(".layout-main")
								.find(".layout-main-section")[0]
								.getBoundingClientRect();
							point.title = title.left;
							point.railInset = point.rail - title.left;
							point.iconInset = point.icon - title.left;
							point.card = card.left;
							point.cardWidth = card.width;
							point.fullWidth =
								$rail[0].ownerDocument.body.classList.contains("full-width");
							expect(point.fullWidth, "Desk width preference").to.eq(fullWidth);
							measurements.push(point);
							cy.writeFile(
								`${Cypress.config(
									"screenshotsFolder"
								)}/../sidebar-alignment-metrics.json`,
								measurements
							);
							if (!baseline) baseline = point;
							for (const key of ["rail", "icon", "railInset", "iconInset"]) {
								if (Math.abs(point[key] - baseline[key]) > 1)
									errors.push(
										`${width}/${theme}/${kind}: ${key} ${point[key]} versus list ${baseline[key]}`
									);
							}
						});
						cy.get("@navRail").trigger("mouseout").trigger("mouseover");
						cy.get("body").should("have.class", "dinext-ws-sidebar-hover-open");
						cy.get("@navRail").then(($rail) => {
							const last = measurements[measurements.length - 1];
							const flyout = $rail
								.find(".list-sidebar.overlay-sidebar")[0]
								.getBoundingClientRect();
							const main = $rail
								.closest(".layout-main")
								.find(".layout-main-section-wrapper")[0]
								.getBoundingClientRect();
							last.flyout = flyout.left;
							last.flyoutInset = flyout.left - last.title;
							if (Math.abs(last.flyout - baseline.rail) > 1)
								errors.push(
									`${width}/${theme}/${kind}: flyout ${last.flyout} versus list ${baseline.rail}`
								);
							if (Math.abs(main.width - last.contentWidth) > 1)
								errors.push(
									`${width}/${theme}/${kind}: hover changed content width`
								);
						});
						cy.screenshot(`rail-alignment-${width}-${theme}-${kind}`, {
							capture: "viewport",
						});
					}
				}
			}
		}
		cy.then(() => {
			cy.writeFile(
				`${Cypress.config("screenshotsFolder")}/../sidebar-alignment-metrics.json`,
				measurements
			);
			cy.then(() => expect(errors, "cross-screen rail coordinates").to.deep.eq([]));
		});
	});
});
