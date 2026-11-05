const { defineConfig } = require(
	process.env.DINEXT_CYPRESS_MODULE || "../frappe/node_modules/cypress"
);

module.exports = defineConfig({
	includeShadowDom: true,
	defaultCommandTimeout: 120000,
	pageLoadTimeout: 120000,
	requestTimeout: 180000,
	viewportWidth: 1440,
	viewportHeight: 900,
	video: false,
	retries: {
		runMode: 0,
		openMode: 0,
	},
	e2e: {
		setupNodeEvents(on, config) {
			const { execFileSync } = require("node:child_process");
			const path = require("node:path");
			const site = process.env.FRAPPE_SITE || "localhost";
			function execute(method, args = []) {
				const output = execFileSync("bench", ["--site", site, "execute", method, ...args], {
					cwd: path.resolve(__dirname, "../.."), encoding: "utf8", timeout: 180000,
				});
				return JSON.parse(output.trim().split("\n").at(-1));
			}
			function run(method) {
				const siteUrl = execute("frappe.utils.get_site_url", ["--args", JSON.stringify([site])]);
				if (new URL(siteUrl).origin !== new URL(config.baseUrl).origin) {
					throw new Error("The Cypress base URL must match the bench site selected by FRAPPE_SITE.");
				}
				return execute(`dinext_timesheets.tests.my_timesheets_cards_ui.${method}`);
			}
			on("task", {
				deadlineCheckpoint(message) {
					process.stdout.write(`DEADLINE: ${message}\n`);
					return null;
				},
				numberCardsSeed: () => run("cli_seed"),
				numberCardsCleanup: () => run("cli_cleanup"),
				numberCardsReopen: () => run("cli_reopen"),
			});
		},
		baseUrl: "http://localhost:8000",
		specPattern: "cypress/integration/**/*.js",
		supportFile: "cypress/support/e2e.js",
		testIsolation: true,
	},
});
