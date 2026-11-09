const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const script = path.resolve(__dirname, '../../dinext_timesheets/public/js/timesheet_deadline_reminder.js');
function setup() {
  assert.ok(fs.existsSync(script), 'The shared Task/Issue reminder is missing');
  const handlers = {}, dialogs = [], storage = new Map(), routes = [];
  const summary = { value: 23, route: ['List', 'User Timesheet'], route_options: {
    timesheet_from: 'author@example.com', ts_date_of_dispatch: ['["is", "set"]', '["<", "2026-11-10"]'] } };
  const ctx = { __: (text) => text, Date, window: { location: { host: 'localhost:8000' } },
    localStorage: { getItem: k => storage.get(k), setItem: (k, v) => storage.set(k, v) },
    frappe: { dinext: {}, model: { can_read: () => true }, session: { user: 'author@example.com' }, ui: { form: { on: (dt, events) => { handlers[dt] = events; } } },
      get_route: () => ["Form", "Task", "TASK-1"], xcall: async () => summary, msgprint: data => dialogs.push(data), hide_msgprint: () => {},
      set_route: route => routes.push(route) } };
  ctx.frappe.ui.Dialog = class {
    constructor(options) {
      this.visible = false; this.$wrapper = { is: () => this.visible };
      dialogs.push({ primary_action: { action: options.primary_action },
        secondary_action: { action: options.secondary_action }, close: () => this.hide() });
    }
    show() { this.visible = true; }
    hide() { this.visible = false; }
  };
  vm.createContext(ctx); vm.runInContext(fs.readFileSync(script, 'utf8'), ctx);
  return { ctx, handlers, dialogs, routes, summary };
}
test('Task reminder navigates to the complete server-provided list', async () => {
  const x = setup(); await x.handlers.Task.refresh({});
  assert.equal(x.dialogs.length, 1);
  x.dialogs[0].primary_action.action();
  assert.equal(JSON.stringify(x.routes[0]), JSON.stringify(x.summary.route));
  assert.equal(JSON.stringify(x.ctx.frappe.route_options), JSON.stringify(x.summary.route_options));
});
test('Remind later suppresses both Task and Issue for the same author', async () => {
  const x = setup(); await x.handlers.Task.refresh({});
  x.dialogs[0].secondary_action.action();
  await x.handlers.Issue.refresh({});
  assert.equal(x.dialogs.length, 1);
  x.ctx.frappe.session.user = 'second@example.com';
  await x.handlers.Issue.refresh({});
  assert.equal(x.dialogs.length, 2);
});
test('No overdue records produce no reminder', async () => {
  const x = setup(); x.summary.value = 0; await x.handlers.Issue.refresh({});
  assert.equal(x.dialogs.length, 0);
});

test('Task remains usable for accounts without timesheet read permission', async () => {
  const x = setup(); x.ctx.frappe.model.can_read = () => false;
  x.ctx.frappe.xcall = async () => { throw new Error('Unauthorized timesheet request'); };
  await x.handlers.Task.refresh({});
  assert.equal(x.dialogs.length, 0);
});

test('Visible reminder is not duplicated by another form refresh', async () => {
  const x = setup(); await x.handlers.Task.refresh({}); await x.handlers.Issue.refresh({});
  assert.equal(x.dialogs.length, 1);
});
test('A response does not open a reminder after leaving Task or Issue', async () => {
  const x = setup(); let resolve;
  x.ctx.frappe.xcall = () => new Promise(done => { resolve = done; });
  const request = x.handlers.Task.refresh({});
  x.ctx.frappe.get_route = () => ['List', 'Task']; resolve(x.summary); await request;
  assert.equal(x.dialogs.length, 0);
});
test('Authentication helpers keep session secrets out of command log labels', () => {
  const commands = {}, labels = [], cookies = [], requests = [];
  const context = { Cypress: { env: key => key === 'sid' ? 'administrator-secret' : null,
    Commands: { add: (name, fn) => { commands[name] = fn; } } },
    cy: { session: (id, fn) => { labels.push(id); fn(); },
      setCookie: (name, value, options) => cookies.push(options), request: options => requests.push(options) } };
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(path.resolve(__dirname, '../../cypress/support/commands.js'), 'utf8'), context);
  commands.login();
  assert.ok(!JSON.stringify(labels).includes('administrator-secret'));
  assert.equal(cookies[0].log, false);
  context.Cypress.env = () => null;
  commands.login('author@example.com', 'password-secret');
  assert.ok(!JSON.stringify(labels).includes('password-secret'));
  assert.equal(requests[0].log, false);
});
