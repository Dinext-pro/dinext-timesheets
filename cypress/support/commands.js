Cypress.Commands.add("login", (email, password) => {
	const sid = Cypress.env("sid");
	if (sid) {
		return cy.session(
			["ut-sid", sid],
			() => {
				cy.setCookie("sid", sid, { httpOnly: true });
			},
			{
				cacheAcrossSpecs: false,
				validate() {
					cy.request("/api/method/frappe.auth.get_logged_user")
						.its("body.message")
						.should("eq", "Administrator");
				},
			}
		);
	}
	if (!email) {
		email = "Administrator";
	}
	if (!password) {
		password = Cypress.env("adminPassword");
	}
	return cy.session(
		[email, password],
		() => {
			cy.request({
				url: "/api/method/login",
				method: "POST",
				body: { usr: email, pwd: password },
			});
		},
		{
			cacheAcrossSpecs: false,
			validate() {
				cy.request("/api/method/frappe.auth.get_logged_user").its("body.message").should("eq", email);
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
