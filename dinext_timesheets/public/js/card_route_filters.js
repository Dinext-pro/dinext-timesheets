/* Preserve historical/blank status values in read-only timesheet filters. */
(() => {
	const prototype = frappe.ui.Filter.prototype;
	if (prototype._dinextTimesheetStatusFilter) return;
	prototype._dinextTimesheetStatusFilter = true;
	const make = prototype.make_field;
	prototype.make_field = function (df, ...args) {
		if (
			df.parent === "User Timesheet" &&
			df.fieldname === "ut_status" &&
			df.fieldtype === "MultiSelect"
		) {
			// The stored history includes values outside today's Select options.
			df.fieldtype = "Data";
			df.options = null;
		}
		return make.call(this, df, ...args);
	};
	const set = prototype.set_values;
	prototype.set_values = function (doctype, field, condition, value) {
		if (
			doctype === "User Timesheet" &&
			field === "ut_status" &&
			["in", "not in"].includes(condition) &&
			Array.isArray(value)
		) {
			// JSON preserves blank/NULL tokens, unlike a joined MultiSelect string.
			value = JSON.stringify(value.map((item) => (item == null ? "" : item)));
		}
		return set.call(this, doctype, field, condition, value);
	};
})();
