Cypress.Commands.add("login", (email = "Administrator", password) => {
	const isAdministrator = email === "Administrator";
	const sid = isAdministrator && !password ? Cypress.env("sid") : null;
	const credential = password || (isAdministrator ? Cypress.env("adminPassword") : null);
	if (!sid && !credential) {
		throw new Error(
			isAdministrator
				? "Cypress requires Administrator credentials for the test site. Set CYPRESS_adminPassword or provide a test session."
				: `Cypress requires a password for test user ${email}.`
		);
	}
	return cy.session(
		[email, sid ? "session" : "password"],
		() => {
			if (sid) {
				return cy.setCookie("sid", sid, { httpOnly: true, log: false });
			}
			return cy
				.request({
					url: "/api/method/login",
					method: "POST",
					body: { usr: email, pwd: credential },
					failOnStatusCode: false,
					log: false,
				})
				.then(({ status }) => {
					expect(status, `Test site login for ${email}`).to.eq(200);
				});
		},
		{
			cacheAcrossSpecs: false,
			validate() {
				return cy
					.request({
						url: "/api/method/frappe.auth.get_logged_user",
						failOnStatusCode: false,
						log: false,
					})
					.then(({ status, body }) => {
						expect(status, `Test site session for ${email}`).to.eq(200);
						expect(body.message).to.eq(email);
					});
			},
		}
	);
});

Cypress.Commands.add("call", (method, args, { failOnStatusCode = true } = {}) => {
	return cy.window().its("frappe.csrf_token").then((csrf_token) => {
		return cy
			.request({
				url: `/api/method/${method}`,
				method: "POST",
				body: args || {},
				failOnStatusCode,
				headers: {
					Accept: "application/json",
					"Content-Type": "application/json",
					"X-Frappe-CSRF-Token": csrf_token,
				},
			})
			.then((res) => {
				if (failOnStatusCode) {
					expect(res.status).to.eq(200);
				}
				return res;
			});
	});
});

Cypress.Commands.add("openDesk", (path) => {
	cy.visit(path || "/app");
	cy.window().its("frappe.csrf_token").should("be.a", "string").and("not.eq", "None");
	cy.window().its("frappe.session.user").should("not.eq", "Guest");
});
