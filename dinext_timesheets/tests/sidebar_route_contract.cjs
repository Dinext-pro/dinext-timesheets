const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");
const app = process.argv[2] || path.resolve(__dirname, "../..");
let route = ["Form", "User Timesheet", "owned-timesheet"];
const classes = new Set();
let onPageChange;
const document = {
	body: {
		classList: {
			add: (x) => classes.add(x),
			remove: (x) => classes.delete(x),
			toggle: (x, flag) => (flag ? classes.add(x) : classes.delete(x)),
			contains: (x) => classes.has(x),
		},
	},
};
const frappe = {
	get_route: () => route,
	listview_settings: {},
	require: () => Promise.resolve(),
};
const $ = () => ({
	on: (_event, fn) => {
		onPageChange = fn;
	},
});
const context = vm.createContext({
	document,
	frappe,
	$,
	window: {},
	add_reprocces_button: () => {},
});
const moduleText = fs.readFileSync(
	`${app}/dinext_timesheets/public/js/user_timesheet/sidebar.js`,
	"utf8"
);
vm.runInContext(moduleText.replaceAll("export ", ""), context);
context.applyTimesheetSidebarHide();
assert.ok(classes.has("ut-hide-desk-sidebar"));
route = ["List", "User Timesheet Position", "List"];
onPageChange();
assert.ok(!classes.has("ut-hide-desk-sidebar"));
context.applyTimesheetSidebarHide();
assert.ok(
	!classes.has("ut-hide-desk-sidebar"),
	"a late form callback must not restyle the position list"
);
vm.runInContext(
	fs.readFileSync(
		`${app}/dinext_timesheets/public/js/user_timesheet/list/status_color.js`,
		"utf8"
	),
	context
);
frappe.listview_settings["User Timesheet"].onload({});
assert.ok(
	!classes.has("ut-hide-desk-sidebar"),
	"a late list onload must not restyle another route"
);
route = ["List", "User Timesheet", "List"];
onPageChange();
assert.ok(classes.has("ut-hide-desk-sidebar"));
console.log("PASS: late form/list callbacks preserve the current route's panel state");
