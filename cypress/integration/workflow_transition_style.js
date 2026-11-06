Cypress.removeAllListeners("uncaught:exception");
const api = "dinext_common.tests.workflow_style_ui";
const setTheme = (theme) =>
	cy.window().then((win) => {
		win.document.documentElement.dataset.theme = theme;
	});

function checkOption(selector, style, token) {
	cy.get(selector)
		.should("have.attr", "data-workflow-style", style)
		.then(($option) => {
			const doc = $option[0].ownerDocument;
			const probe = doc.createElement("span");
			const darkTokens = { success: "--green-300", danger: "--red-300" };
			probe.style.color = `var(${
				doc.documentElement.dataset.theme === "dark" ? darkTokens[style] : token
			})`;
			doc.body.appendChild(probe);
			expect(doc.defaultView.getComputedStyle($option[0]).color).to.eq(
				doc.defaultView.getComputedStyle(probe).color
			);
			probe.remove();
		});
}

context(
	"Timesheet Workflow destination styles",
	{ viewportWidth: 1280, viewportHeight: 720 },
	() => {
		before(() => {
			cy.login();
			cy.openDesk("/app");
			cy.call(`${api}.seed_workflow_styles`, { include_timesheets: 1 }).then((res) => {
				Cypress.env("style", res.body.message);
			});
		});
		after(() => {
			cy.login();
			cy.openDesk("/app");
			cy.call(`${api}.cleanup_workflow_styles`);
		});

		it("Timesheet form menu", () => {
			cy.login();
			cy.visit(`/app/user-timesheet/${encodeURIComponent(Cypress.env("style").timesheet)}`);
			cy.get(
				'.page-container:visible .inner-group-button[data-label="Workflow"] > button'
			).click();
			for (const theme of ["light", "dark"]) {
				setTheme(theme);
				checkOption(
					'.inner-group-button .dinext-workflow-transition[data-workflow-style="success"]',
					"success",
					"--text-on-green"
				);
				checkOption(
					'.inner-group-button .dinext-workflow-transition[data-workflow-style="danger"]',
					"danger",
					"--text-on-red"
				);
				cy.get(
					'.inner-group-button .dinext-workflow-transition[data-workflow-style="success"] svg'
				).should("exist");
				cy.screenshot(`timesheet-workflow-${theme}`);
			}
		});

		it("Position list choices", () => {
			cy.login();
			cy.visit("/app/user-timesheet-position");
			cy.get(".dinext-utp-action-select").should("be.visible");
			for (const theme of ["light", "dark"]) {
				setTheme(theme);
				checkOption(
					'.dinext-utp-action-select option[data-workflow-style="success"]',
					"success",
					"--text-on-green"
				);
				checkOption(
					'.dinext-utp-action-select option[data-workflow-style="danger"]',
					"danger",
					"--text-on-red"
				);
				cy.screenshot(`timesheet-position-list-${theme}`);
			}
			cy.get(".list-row-checkbox").first().check({ force: true });
			cy.contains(".page-container:visible button", "Apply workflow action").click();
			checkOption(
				'.modal:visible select option[data-workflow-style="success"]',
				"success",
				"--text-on-green"
			);
			checkOption(
				'.modal:visible select option[data-workflow-style="danger"]',
				"danger",
				"--text-on-red"
			);
			cy.get(".modal:visible .modal-header .btn-modal-close").click();
			// Exercise the legacy client renderer against the same synthetic transitions.
			cy.intercept("GET", "/app/user-timesheet-position", (request) => {
				request.continue((response) => {
					response.body = response.body.replace(
						/"enable_parallel_workflow_approval"\s*:\s*true/,
						'"enable_parallel_workflow_approval":false'
					);
				});
			});
			cy.visit("/app/user-timesheet-position");
			cy.window().its("frappe.boot.enable_parallel_workflow_approval").should("eq", false);
			cy.get("select.action-dropdown").should("be.visible");
			for (const theme of ["light", "dark"]) {
				setTheme(theme);
				checkOption(
					'select.action-dropdown option[data-workflow-style="success"]',
					"success",
					"--text-on-green"
				);
				checkOption(
					'select.action-dropdown option[data-workflow-style="danger"]',
					"danger",
					"--text-on-red"
				);
				cy.screenshot(`timesheet-legacy-position-list-${theme}`);
			}
		});
	}
);
