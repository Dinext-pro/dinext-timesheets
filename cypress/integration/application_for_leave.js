const helper = "dinext_timesheets.tests.application_for_leave_ui";

describe("Application For Leave", () => {
	const marker = "afl-cypress-" + Cypress._.times(12, () => Cypress._.random(0, 35).toString(36)).join("");
	const doctype = "Application For Leave";
	let fixture;

	before(() => {
		cy.login();
		cy.openDesk();
		cy.call(helper + ".seed", { marker }).its("body.message").then((data) => {
			fixture = data;
		});
	});

	after(() => {
		if (!fixture) return;
		cy.login();
		cy.openDesk();
		cy.call(helper + ".cleanup", { marker });
	});

	it("displays partial days, the total excluding holidays, and the matching project", () => {
		cy.login(fixture.user, fixture.password);
		cy.openDesk("/app/application-for-leave/" + encodeURIComponent(fixture.leave));
		cy.window().should((win) => {
			expect(win.cur_frm?.doc?.name).to.eq(fixture.leave);
			const leave = win.cur_frm.doc;
			expect(leave.status).to.eq("Pending Approval");
			expect(Number(leave.alfrom_hours)).to.eq(3);
			expect(Number(leave.alto_hours)).to.eq(4);
			expect(Number(leave.al_total_hours)).to.eq(7);
			expect(leave.user_projects.map((row) => row.project)).to.deep.eq([marker]);
		});
		cy.get(".page-container:visible [data-fieldname='al_total_hours']").scrollIntoView()
			.should("be.visible").and("contain.text", "7");
		cy.get(".page-container:visible [data-fieldname='user_projects']").scrollIntoView()
			.should("be.visible").and("contain.text", marker);
		cy.noPermissionDialog();
		cy.screenshot("leave-hours-and-project", { capture: "viewport" });
	});

	it("refuses a new application sharing the last date of a pending application", () => {
		cy.login(fixture.user, fixture.password);
		cy.openDesk("/app/application-for-leave/" + encodeURIComponent(fixture.leave));
		cy.window().should((win) => expect(win.cur_frm?.doc?.name).to.eq(fixture.leave));
		cy.window().then((win) => {
			const draft = win.frappe.model.get_new_doc(doctype);
			return win.frappe.set_route("Form", doctype, draft.name);
		});
		cy.window().should((win) => {
			expect(win.cur_frm?.is_new()).to.be.ok;
			expect(win.cur_frm.doctype).to.eq(doctype);
		});
		cy.window().then(async (win) => {
			const form = win.cur_frm;
			await form.set_value("alworker", fixture.worker);
			await form.set_value("altype_of_leave", marker);
			await form.set_value("alfrom_date", fixture.end);
			await form.set_value("alto_date", fixture.overlap_end);
		});
		cy.intercept("POST", "**/api/method/frappe.desk.form.save.savedocs").as("saveLeave");
		cy.contains(".page-container:visible .primary-action", "Save").click();
		cy.wait("@saveLeave").its("response.statusCode").should("eq", 417);
		cy.contains(".modal:visible", "This Worker already has a leave application that overlaps the selected dates.")
			.should("be.visible");
		cy.window().should((win) => expect(win.cur_frm.is_new()).to.be.ok);
		cy.screenshot("leave-overlap-refused", { capture: "viewport" });
		cy.call("frappe.client.get_count", { doctype, filters: { alworker: fixture.worker } })
			.its("body.message").should("eq", 1);
		cy.call("frappe.client.get_count", {
			doctype: "Workflow Task",
			filters: {
				reference_doctype: doctype,
				reference_name: fixture.end + " - " + fixture.overlap_end + " -" + fixture.user,
			},
		}).its("body.message").should("eq", 0);
	});
});
