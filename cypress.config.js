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
	env: {
		adminPassword: "admin",
	},
	e2e: {
		setupNodeEvents(on) {
			const { execFileSync } = require("node:child_process");
			const path = require("node:path");
			function run(method) {
				const output = execFileSync("bench", ["--site", "localhost", "execute",
					`dinext_timesheets.tests.my_timesheets_cards_ui.${method}`], {
					cwd: path.resolve(__dirname, "../.."), encoding: "utf8", timeout: 180000,
				});
				return JSON.parse(output.trim().split("\n").at(-1));
			}
			on("task", {
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
