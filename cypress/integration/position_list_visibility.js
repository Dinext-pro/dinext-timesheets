Cypress.removeAllListeners("uncaught:exception");
const helper = "dinext_timesheets.tests.position_visibility_ui";
const source = "User Timesheet Position";
let fixture;

function adminConfigure(args = {}) {
  cy.login();
  cy.openDesk("/app/timesheet-settings/Timesheet%20Settings");
  cy.window({ timeout: 60000 }).should((win) => {
    expect(win.cur_frm?.doctype).to.eq("Timesheet Settings");
    expect(win.cur_frm?.fields_dict.visible_list_statuses?.grid).to.exist;
  });
  cy.call(`${helper}.configure_visibility`, args);
}

function openPositions(user, count) {
  cy.login(user, fixture.password);
  cy.openDesk(
    `/app/user-timesheet-position?user_timesheet=${encodeURIComponent(
      fixture.timesheet
    )}`
  );
  assertRows(count);
}

function assertRows(count) {
  cy.window({ timeout: 60000 }).should((win) => {
    expect(win.cur_list?.doctype).to.eq(source);
    expect(win.cur_list.data.length).to.eq(count);
    expect(
      win.cur_list.data.every((r) => r.user_timesheet === fixture.timesheet)
    ).to.eq(true);
  });
}

function assertCount(expected) {
  cy.call("frappe.desk.reportview.get_count", {
    doctype: source,
    filters: JSON.stringify([
      [source, "user_timesheet", "=", fixture.timesheet],
    ]),
  }).then((res) => expect(res.body.message).to.eq(expected));
}

context(
  "Explicit timesheet position visibility",
  { defaultCommandTimeout: 30000 },
  () => {
    before(() => {
      cy.login();
      cy.openDesk("/app");
      cy.call(`${helper}.seed_visibility`, {}, { timeout: 180000 }).then(
        (res) => {
          fixture = res.body.message;
        }
      );
    });
    after(() => {
      cy.login();
      cy.openDesk("/app");
      cy.call(`${helper}.cleanup_visibility`, {}, { timeout: 180000 });
    });

    it("uses explicit statuses and an empty allowlist, with settings in both themes", () => {
      adminConfigure();
      cy.window().then((win) => win.cur_frm.reload_doc());
      for (const theme of ["light", "dark"]) {
        cy.window().then((win) => win.frappe.ui.set_theme(theme));
        cy.get(
          '.page-container:visible [data-fieldname="visible_section"]'
        ).should("contain", "Visible In Position List");
        cy.get(
          '.page-container:visible [data-fieldname="visible_list_statuses"] .grid-heading-row'
        ).should("contain", "Open WF Task");
        cy.get(
          '.page-container:visible [data-fieldname="hidden_list_statuses"]'
        ).should("not.be.visible");
        cy.screenshot(`visible-position-settings-${theme}`, {
          capture: "viewport",
        });
      }
      openPositions(fixture.approver, 20);
      assertCount(20);
      cy.window().then((win) => {
        win.cur_list.page_length = 5;
        win.cur_list.start = 0;
        return win.cur_list.refresh();
      });
      assertRows(5);
      assertCount(20);
      adminConfigure({ empty: 1 });
      openPositions(fixture.approver, 0);
      assertCount(0);
    });

    it("requires the user's open task and removes completed tasks on refresh", () => {
      adminConfigure({ gated: 1 });
      openPositions(fixture.approver, 16);
      assertCount(16);
      cy.window().should((win) => {
        const names = win.cur_list.data.map((r) => r.name);
        expect(names).to.include(fixture.positions[0].name);
        for (const index of [1, 2, 3, 4, 5])
          expect(names).not.to.include(fixture.positions[index].name);
      });
      cy.call(`${helper}.complete_visibility_task`, {}).then((res) => {
        cy.window().should((win) => expect(win.cur_list.last_args).to.eq(null));
        cy.window().then((win) => win.cur_list.refresh());
        assertRows(15);
        cy.window().should((win) =>
          expect(win.cur_list.data.map((r) => r.name)).not.to.include(
            res.body.message.position
          )
        );
      });
      assertCount(15);
      openPositions(fixture.viewer, 2);
      assertCount(2);
      cy.window().should((win) =>
        expect(win.cur_list.data.map((r) => r.name)).to.have.members([
          fixture.positions[0].name,
          fixture.positions[2].name,
        ])
      );
    });

    it("keeps the converted settings and preserves an intentionally empty edit on reapply", () => {
      adminConfigure({ restore_initial: 1 });
      cy.call(`${helper}.reapply_conversion`, {}).then((res) =>
        expect(res.body.message).to.deep.eq(fixture.initial_visible)
      );
      adminConfigure({ empty: 1 });
      cy.call(`${helper}.reapply_conversion`, {}).then((res) =>
        expect(res.body.message).to.deep.eq([])
      );
      cy.reload();
      cy.window({ timeout: 60000 }).should((win) => {
        expect(win.cur_frm?.doctype).to.eq("Timesheet Settings");
        expect(win.cur_frm.doc.visible_list_statuses).to.have.length(0);
      });
    });
  }
);
