Cypress.removeAllListeners("uncaught:exception");
import {
	seed,
	cleanup,
	dialog,
	openList,
	openForm,
	formControl,
	role,
	total,
	close,
} from "../../../project_workload_assignment/cypress/support/limits_dialog";
let fixture;
context("Timesheet shared limit details", { defaultCommandTimeout: 30000 }, () => {
	before(() =>
		seed().then((value) => {
			fixture = value;
		})
	);
	after(cleanup);
	it("shows identical saved details on the timesheet form and position list", () => {
		let formText;
		openForm(fixture);
		formControl(fixture).click();
		total(fixture).should("contain", "280.0").and("contain", "322.0").and("contain", "115%");
		role(fixture)
			.invoke("text")
			.then((text) => {
				formText = text.replace(/\s+/g, " ").trim();
			});
		close();
		openList(fixture);
		cy.get(".dinext-utp-list .plan-fact-button").click();
		role(fixture)
			.invoke("text")
			.should((text) => {
				expect(text.replace(/\s+/g, " ").trim()).to.eq(formText);
			});
		close();
	});
	it("includes an unsaved day-hour edit once without changing saved facts", () => {
		openForm(fixture);
		cy.window().then((win) => {
			const api = win.cur_frm.ut.table.api;
			const node = api.getRowNode(fixture.editing_position);
			api.ensureNodeVisible(node, "middle");
			api.startEditingCell({ rowIndex: node.rowIndex, colKey: `day_${fixture.date}` });
		});
		cy.get(".ag-cell-inline-editing input").clear();
		cy.get(".ag-cell-inline-editing input").type("48{enter}");
		formControl(fixture).click();
		total(fixture).should("contain", "330.0");
		role(fixture).find('tr[data-status="Editing"]').should("contain", "48.0");
		cy.call("frappe.client.get", {
			doctype: "User Timesheet Position",
			name: fixture.editing_position,
		}).then((res) => {
			expect(res.body.message.table[0].hours).to.eq(40);
		});
		close();
		cy.window().then((win) => {
			win.cur_frm.doc.__unsaved = 0;
		});
		openList(fixture);
		cy.get(".dinext-utp-list .plan-fact-button").click();
		total(fixture).should("contain", "322.0");
		close();
	});
});
