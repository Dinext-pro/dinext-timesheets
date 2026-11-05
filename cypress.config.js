const { defineConfig } = require(process.env.DINEXT_CYPRESS_MODULE || "../frappe/node_modules/cypress");
module.exports = defineConfig({
	defaultCommandTimeout: 60000, pageLoadTimeout: 120000, requestTimeout: 120000,
	responseTimeout: 120000, viewportWidth: 1440, viewportHeight: 1000, video: false,
	e2e: { setupNodeEvents(on) { on("task", { deadlineCheckpoint(message) { process.stdout.write(`DEADLINE: ${message}\n`); return null; } }); }, baseUrl: "http://localhost:8000", specPattern: "cypress/integration/**/*.js", supportFile: "cypress/support/e2e.js" },
});
