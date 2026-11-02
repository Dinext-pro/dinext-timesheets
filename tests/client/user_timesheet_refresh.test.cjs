const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const entry = fs.readFileSync(
  path.resolve(
    __dirname,
    "../../dinext_timesheets/public/js/user_timesheet/entry.js"
  ),
  "utf8"
);
const tick = () => new Promise((resolve) => setImmediate(resolve));
function deferred() {
  let resolve;
  const promise = new Promise((done) => {
    resolve = done;
  });
  return { promise, resolve };
}
function formHarness(api) {
  let handlers;
  const form = {
    doctype: "User Timesheet",
    doc: { name: "timesheet", modified: "1" },
    is_new: () => false,
    buttons: [],
  };
  const context = {
    console,
    cur_frm: null,
    document: { body: { classList: { add() {} } } },
    window: { UserTimesheet: api },
    frappe: {
      require(_assets, ready) {
        ready();
      },
      ui: {
        form: {
          on(_doctype, value) {
            handlers = value;
          },
        },
      },
    },
  };
  vm.runInNewContext(entry, context);
  return { form, refresh: () => handlers.refresh(form) };
}

test("restores Workflow controls when Frappe refreshes during a dashboard load", async () => {
  const dashboard = deferred();
  let dashboards = 0;
  const { form, refresh } = formHarness({
    ensureMounted: async () => {},
    setupFormChrome: async (frm) => {
      frm.buttons = ["Submit for Approval"];
    },
    showTimesheetDashboard: async () => {
      if (++dashboards === 1) await dashboard.promise;
    },
  });
  refresh();
  await tick();
  assert.deepEqual(form.buttons, ["Submit for Approval"]);
  // refresh_header clears these before dispatching the next refresh handler.
  form.buttons = [];
  form.doc.modified = "2";
  refresh();
  const completion = form._ut_load_promise;
  dashboard.resolve();
  await completion;
  assert.deepEqual(form.buttons, ["Submit for Approval"]);
});

test("coalesces rapid refreshes and finishes with the latest card controls", async () => {
  const mount = deferred();
  let mounts = 0;
  const { form, refresh } = formHarness({
    ensureMounted: async () => {
      if (++mounts === 1) await mount.promise;
    },
    setupFormChrome: async (frm) => {
      frm.buttons = [frm.doc.name];
    },
    showTimesheetDashboard: async () => {},
  });
  refresh();
  for (const name of ["second", "third", "latest"]) {
    form.doc = { name, modified: name };
    form.buttons = [];
    refresh();
  }
  const completion = form._ut_load_promise;
  mount.resolve();
  await completion;
  assert.deepEqual(form.buttons, ["latest"]);
  assert.equal(mounts, 2);
});
