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
const dashboardSource = fs.readFileSync(
  path.resolve(
    __dirname,
    "../../dinext_timesheets/public/js/user_timesheet/dashboard.js"
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

const pendingRows = [
  { reference_name: "position-1", approver: "alice", approver_name: "Alice" },
];
const rebuildRounds = [{ reference_name: "position-1", name: "round-1" }];
function dashboardHarness(request = async () => undefined) {
  const messages = [];
  const requests = [];
  const connections = new Set();
  let rebuilds = [];
  let route = "Form/User Timesheet/timesheet";
  function selection(nodes) {
    return {
      remove() {
        for (const node of nodes) messages.splice(messages.indexOf(node), 1);
      },
      addClass(value) {
        for (const node of nodes) node.classes.push(value);
        return this;
      },
      last: () => selection(nodes.slice(-1)),
    };
  }
  function find(selector) {
    const classes = selector.split(".").filter(Boolean);
    return selection(messages.filter((item) => classes.every((value) => item.classes.includes(value))));
  }
  function addMessage(text, ...classes) {
    messages.push({ text, classes: ["form-message", ...classes] });
  }
  const form = {
    doctype: "User Timesheet",
    doc: { doctype: "User Timesheet", name: "timesheet", ut_status: "Approved" },
    is_new: () => false,
    layout: { message: { find, children: find } },
    dashboard: {
      wrapper: { find },
      add_comment(text, color) { addMessage(text, color); },
      clear_headline() { messages.splice(0); },
      links_area: {
        show: () => connections.add("links"),
        hide: () => connections.delete("links"),
      },
    },
    ut: {
      rows: [{ rowType: "position", id: "position-1", approver_tooltip: "Old approver" }],
      table: { api: { refreshCells() {} } },
    },
  };
  const names = (rows) => rows.map((row) => `Shared ${row.approver_name}`);
  const context = {
    console,
    __: (value, args = []) => value.replace(/\{(\d+)\}/g, (_, index) => args[index]),
    document: { body: { classList: {
      add: (value) => connections.add(value),
      remove: (value) => connections.delete(value),
    } } },
    frappe: {
      session: { user: "viewer" },
      get_route_str: () => route,
      require() {},
      datetime: { str_to_user: (value) => value },
      model: { can_read: () => true },
      utils: { comma_and: (values) => values.join(", "), escape_html: (value) => value },
      dinext: {
        async refreshWorkflowComments() {},
        getPendingApproverNames: names,
        paintPendingApprovers(_frm, rows) {
          find(".dinext-pending-approvers").remove();
          if (rows.length) addMessage(`Action expected from: ${names(rows).join(", ")}`, "blue", "dinext-pending-approvers");
        },
        paintRebuildRounds(_dashboard, rows) { rebuilds = [...rows]; },
        async workflowRequest(method, args) {
          const kind = method.endsWith("get_pending_approvers") ? "pending"
            : method.endsWith("get_deadline_state") ? "deadline" : "rebuild";
          requests.push({ kind, args });
          const result = await request(kind, args);
          if (result !== undefined) return result;
          return kind === "pending" ? pendingRows
            : kind === "deadline" ? { overdue: true, deadline: "2026-11-01" } : rebuildRounds;
        },
      },
    },
  };
  vm.runInNewContext(dashboardSource.replace("export async function", "async function"), context);
  return {
    form, messages, requests, addMessage,
    setRoute(value) { route = value; },
    show: () => context.showTimesheetDashboard(form),
    snapshot: () => JSON.stringify({ messages, rebuilds, connections: [...connections], rows: form.ut.rows }),
  };
}

test("uses shared approver rendering and tooltips while preserving unrelated messages", async () => {
  const harness = dashboardHarness();
  harness.addMessage("Other blue message", "blue");
  harness.addMessage("Other orange message", "orange");
  harness.addMessage("Other message", "gray");
  await harness.show();
  await harness.show();
  assert.deepEqual(harness.messages.map((item) => item.text), [
    "Other blue message", "Other orange message", "Other message",
    "Action expected from: Shared Alice",
    "Timesheet is overdue. Submission deadline: 2026-11-01",
  ]);
  assert.equal(harness.messages.filter((item) => item.classes.includes("dinext-timesheet-deadline")).length, 1);
  assert.equal(harness.form.ut.rows[0].approver_tooltip, "Shared Alice");
  assert.ok(harness.snapshot().includes("ut-show-connections"));
  assert.ok(harness.snapshot().includes("round-1"));
});

for (const state of ["new", "missing name", "empty", "pending failure"]) {
  test(`clears owned approver and overdue messages and tooltips for ${state} records`, async () => {
    const harness = dashboardHarness(async (kind) => {
      if (kind === "pending" && state === "pending failure") throw new Error("unavailable");
      return kind === "pending" ? [] : kind === "deadline" ? { overdue: false } : [];
    });
    harness.addMessage("Keep this message", "orange");
    harness.addMessage("Old pending", "blue", "dinext-pending-approvers");
    harness.addMessage("Old deadline", "orange", "dinext-timesheet-deadline");
    if (state === "new") harness.form.is_new = () => true;
    if (state === "missing name") harness.form.doc.name = "";
    await harness.show();
    assert.deepEqual(harness.messages.map((item) => item.text), ["Keep this message"]);
    assert.equal(harness.form.ut.rows[0].approver_tooltip, "");
    if (state === "new" || state === "missing name") assert.equal(harness.requests.length, 0);
  });
}

for (const kind of ["pending", "deadline", "rebuild"]) {
  for (const changed of ["name", "doctype", "generation", "route"]) {
    test(`ignores a delayed ${kind} response after the document ${changed} changes`, async () => {
      const response = deferred();
      let delayed = false;
      const harness = dashboardHarness(async (requestedKind) => {
        if (requestedKind === kind && !delayed) {
          delayed = true;
          return response.promise;
        }
      });
      const first = harness.show();
      await tick();
      assert.equal(delayed, true);
      if (changed === "generation") {
        await harness.show();
      } else {
        if (changed === "route") {
          harness.setRoute("List/User Timesheet/List");
        } else {
          harness.form.doc = { ...harness.form.doc, [changed]: `another-${changed}` };
          if (changed === "doctype") harness.form.doctype = harness.form.doc.doctype;
        }
        harness.form.ut.rows[0].approver_tooltip = "Current document approver";
        harness.addMessage("Current document message", "blue");
      }
      const snapshot = harness.snapshot();
      response.resolve(kind === "pending" ? [
        { reference_name: "position-1", approver: "old", approver_name: "Old" },
      ] : kind === "deadline" ? { overdue: true, deadline: "old deadline" }
        : [{ reference_name: "old-position", name: "old-round" }]);
      await first;
      assert.equal(harness.snapshot(), snapshot);
    });
  }
}
