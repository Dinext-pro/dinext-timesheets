import assert from "node:assert/strict";
import test from "node:test";

const DATE = "2026-09-03";
const DAY = `day_${DATE}`;

globalThis.flt = (value) => {
	const number = Number.parseFloat(value);
	return Number.isFinite(number) ? number : 0;
};

globalThis.__ = (message, values) => {
	if (values == null) {
		return message;
	}
	const list = Array.isArray(values) ? values : [values];
	return message.replace(/\{(\d+)\}/g, (_match, index) => list[Number(index)]);
};

const prints = [];
const composers = [];

globalThis.frappe = {
	boot: {},
	session: { user: "owner@example.com" },
	user: { has_role: () => false },
	utils: { escape_html: (value) => String(value) },
	datetime: { nowdate: () => "2026-09-03" },
	call: async () => ({ message: [] }),
	msgprint: (message) => {
		prints.push(message);
	},
	views: {
		CommunicationComposer: function Composer(options) {
			composers.push(options);
		},
	},
};

const { guardEditableTimesheet, reportTimesheetError } = await import(
	"../../dinext_timesheets/public/js/user_timesheet/submit.js"
);

function resetClient() {
	prints.length = 0;
	composers.length = 0;
	frappe.boot = {};
	frappe.call = async () => ({ message: [] });
}

function row(overrides = {}) {
	return {
		id: "row-1",
		rowType: "position",
		project: "PROJ-1",
		document_type: "Task",
		document_name: "TASK-1",
		document_label: "Task One",
		project_role: "Developer",
		isNew: false,
		[DAY]: 8,
		[`desc_${DATE}`]: "did the work",
		...overrides,
	};
}

function form(overrides = {}) {
	const frm = {
		doc: { name: "UT-1", ut_status: "Draft" },
		docname: "UT-1",
		is_dirty: () => false,
		deletedPositions: [],
		ts_positions: [{ name: "row-1" }],
		template_doc: {
			hours_on_date: 8,
			minimum_hours: 0,
			maximum_hours: 0,
			_is_mandatory: false,
		},
		ut: {
			dates: [DATE],
			holidays: [],
			workHours: [],
			rows: [row()],
			invalidCells: new Map(),
		},
	};
	return Object.assign(frm, overrides);
}

const checks = { runs_timesheet_checks: true };

function dialog() {
	assert.equal(prints.length, 1);
	assert.equal(prints[0].title, "Timesheet Validation Errors");
	assert.equal(prints[0].as_list, true);
	return prints[0].message;
}

test.beforeEach(resetClient);

test("unsaved positions ask to save before the error list", async () => {
	for (const frm of [
		form({ deletedPositions: ["UTP-1"] }),
		form({ ts_positions: [{ name: "new_1", new: true }] }),
	]) {
		prints.length = 0;
		assert.equal(await guardEditableTimesheet(frm, checks), false);
		assert.deepEqual(prints, ["Save the timesheet first"]);
	}
});

test("a row missing project, task, role, and hours marks those cells", async () => {
	const frm = form();
	frm.ut.rows = [
		row({
			project: "",
			document_name: "",
			project_role: "",
			[DAY]: 0,
			[`desc_${DATE}`]: "",
		}),
	];
	frm.ut.holidays = [{ holiday_date: DATE }];
	assert.equal(await guardEditableTimesheet(frm, checks), false);
	assert.deepEqual(dialog(), [
		"Select a project in row 1",
		"Select a request or task in row 1",
		"Select a project role in row 1",
		"Enter hours in row 1",
	]);
	assert.equal(
		frm.ut.invalidCells.get("row-1::project_label"),
		"Select a project in row 1"
	);
	assert.equal(
		frm.ut.invalidCells.get("row-1::document_label"),
		"Select a request or task in row 1"
	);
	assert.equal(
		frm.ut.invalidCells.get("row-1::project_role"),
		"Select a project role in row 1"
	);
	assert.equal(frm.ut.invalidCells.get("row-1::total"), "Enter hours in row 1");
});

test("a mandatory description is required on a filled day", async () => {
	const frm = form();
	frm.template_doc = { ...frm.template_doc, _is_mandatory: true };
	frm.ut.rows = [row({ [`desc_${DATE}`]: "  " })];
	assert.equal(await guardEditableTimesheet(frm, checks), false);
	const message = "Description is not filled for 2026-09-03 on task Task One";
	assert.deepEqual(dialog(), [message]);
	assert.equal(frm.ut.invalidCells.get(`row-1::${DAY}`), message);
});

test("duplicate project, task, and role rows are rejected", async () => {
	const frm = form();
	frm.ut.rows = [
		row({ id: "row-1", [DAY]: 4 }),
		row({ id: "row-2", [DAY]: 4 }),
	];
	assert.equal(await guardEditableTimesheet(frm, checks), false);
	const message = "Duplicate rows 1, 2: same project, task, and role";
	assert.deepEqual(dialog(), [message]);
	for (const id of ["row-1", "row-2"]) {
		assert.equal(frm.ut.invalidCells.get(`${id}::project_label`), message);
		assert.equal(frm.ut.invalidCells.get(`${id}::document_label`), message);
		assert.equal(frm.ut.invalidCells.get(`${id}::project_role`), message);
	}
});

test("a working day without positions asks to add them", async () => {
	const frm = form();
	frm.ut.rows = [];
	frm.ts_positions = [];
	assert.equal(await guardEditableTimesheet(frm, checks), false);
	assert.deepEqual(dialog(), ["Add positions for approval"]);
	assert.equal(frm.ut.invalidCells.size, 0);
});

test("a day below the minimum marks the total row", async () => {
	const frm = form();
	frm.ut.rows = [row({ [DAY]: 1 })];
	assert.equal(await guardEditableTimesheet(frm, checks), false);
	const message = "2026-09-03 cannot be less than 8 hours.";
	assert.deepEqual(dialog(), [message]);
	assert.equal(frm.ut.invalidCells.get(`ut_day_totals::${DAY}`), message);
});

test("a day above the maximum marks the total row", async () => {
	const frm = form();
	frm.ut.rows = [row({ [DAY]: 12 })];
	assert.equal(await guardEditableTimesheet(frm, checks), false);
	const message = "2026-09-03 cannot be more than 8 hours.";
	assert.deepEqual(dialog(), [message]);
	assert.equal(frm.ut.invalidCells.get(`ut_day_totals::${DAY}`), message);
});

test("a blocking planned-hours limit is a submit error", async () => {
	frappe.call = async () => ({
		message: [
			{
				status: "block",
				planned_hours: 10,
				limit: 100,
				total_hours: 12,
				task_subject: "Subject",
				role: "Developer",
			},
		],
	});
	assert.equal(await guardEditableTimesheet(form(), checks), false);
	assert.deepEqual(dialog(), [
		'Work efforts for task "Subject" (role: Developer) exceeded the blocking limit (10 h.) by 2 hour(s).',
	]);
});

test("missing mandatory planned hours are a submit error", async () => {
	frappe.call = async () => ({
		message: [
			{
				status: "block",
				planned_hours: 0,
				task_subject: "Subject",
				role: "Developer",
			},
		],
	});
	assert.equal(await guardEditableTimesheet(form(), checks), false);
	assert.deepEqual(dialog(), [
		'Mandatory planned work efforts are not defined for task "Subject" (role: Developer)',
	]);
});

test("a failed limits call is reported as a submit error", async () => {
	frappe.call = async () => {
		throw new Error("boom");
	};
	assert.equal(await guardEditableTimesheet(form(), checks), false);
	assert.deepEqual(dialog(), [
		"Error checking planned work efforts and limits: boom",
	]);
});

test("actions that do not check the timesheet skip validation", async () => {
	const frm = form();
	frm.ut.rows = [row({ project: "" })];
	assert.equal(await guardEditableTimesheet(frm, {}), true);
	assert.deepEqual(prints, []);
	assert.equal(frm.ut.invalidCells.size, 0);
});

test("a validation error is shown instead of mailed", () => {
	frappe.boot = { error_report_email: "ops@example.com" };
	reportTimesheetError(form(), {
		responseJSON: {
			exc_type: "ValidationError",
			exception: "Position UTP-1: project is required",
		},
	});
	assert.deepEqual(composers, []);
	assert.equal(prints.length, 1);
	assert.equal(prints[0].title, "Error saving timesheet");
	assert.equal(prints[0].message, "Position UTP-1: project is required");
});

test("a non-validation error with a report address opens the composer", () => {
	frappe.boot = { error_report_email: "ops@example.com" };
	reportTimesheetError(form(), {
		responseJSON: { exc_type: "PermissionError", exception: "nope" },
	});
	assert.deepEqual(prints, []);
	assert.equal(composers.length, 1);
	assert.equal(composers[0].recipients, "ops@example.com");
});
