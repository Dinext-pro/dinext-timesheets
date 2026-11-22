"""Project authorized workflow mail rows into the Timesheets email layout."""

from frappe import _

from dinext_common.workflow_approval.email_presentation import date_label, document_summary, full_name, number_label


def hours_breakdown(details, user):
	unit = _("h", context="WorkflowTimesheetHours")
	entries = []
	for item in details or []:
		hours = float(item.get("hours") or 0)
		if hours == 0:
			continue
		text = number_label(hours, user) + " " + unit
		description = (item.get("description") or "").strip()
		entries.append(text + (" — " + description if description else ""))
	return ", ".join(entries)


def timesheet_deadline_groups(rows, user):
	"""One permitted parent, with each approver's earliest missed deadline."""
	from dinext_common.workflow_approval.notifications import _aware_utc

	sheets = {}
	for row in rows:
		if not row.get("timesheet_name"):
			continue
		sheet = sheets.setdefault(
			row["timesheet_name"],
			dict(
				name=row["timesheet_name"],
				link=row["link"],
				author_name=full_name(row.get("author")),
				title=_("Timesheet")
				+ " · "
				+ date_label(row.get("period_from"), user, date_only=True)
				+ " — "
				+ date_label(row.get("period_to"), user, date_only=True),
				overdues={},
			),
		)
		key = row.get("approver") or row.get("approver_name") or ""
		previous = sheet["overdues"].get(key)
		if previous is None:
			sheet["overdues"][key] = dict(row)
			continue
		if row.get("due") and (
			not previous.get("due") or _aware_utc(row["due"]) < _aware_utc(previous["due"])
		):
			previous.update(due=row["due"], due_label=row["due_label"])
		previous["overdue_hours"] = max(
			float(previous.get("overdue_hours") or 0), float(row.get("overdue_hours") or 0)
		)
		previous["overdue_label"] = number_label(previous["overdue_hours"], user)
	for sheet in sheets.values():
		sheet["overdues"] = sorted(
			sheet["overdues"].values(), key=lambda item: (item.get("approver_name") or "").casefold()
		)
	return sorted(sheets.values(), key=lambda item: (item["title"], item["author_name"], item["name"]))


def timesheet_groups(rows, user):
	authors = {}
	for row in rows:
		if not row.get("timesheet_name"):
			continue
		author = row.get("author") or ""
		group = authors.setdefault(author, dict(author_name=full_name(author), sheets={}))
		sheet = group["sheets"].setdefault(
			row["timesheet_name"],
			dict(
				name=row["timesheet_name"],
				title=_("Timesheet")
				+ " · "
				+ date_label(row.get("period_from"), user, date_only=True)
				+ " — "
				+ date_label(row.get("period_to"), user, date_only=True),
				link=row["link"],
				positions={},
			),
		)
		position = sheet["positions"].setdefault(
			row.get("position_name") or row["name"], dict(row, overdues=[])
		)
		if row.get("due"):
			position["overdues"].append(
				dict(
					approver_name=row.get("approver_name"),
					due_label=row["due_label"],
					overdue_label=row["overdue_label"],
				)
			)
	result = []
	for author in sorted(authors.values(), key=lambda item: item["author_name"].casefold()):
		sheets = []
		for sheet in author["sheets"].values():
			positions = sorted(
				sheet["positions"].values(),
				key=lambda item: (int(item.get("ordinal") or 0), item.get("position_name") or ""),
			)
			sheet.update(
				positions=positions,
				count=len(positions),
				hours=sum(float(item.get("hours") or 0) for item in positions),
			)
			sheet["hours_label"] = number_label(sheet["hours"], user)
			sheets.append(sheet)
		author["sheets"] = sorted(sheets, key=lambda item: item["name"])
		result.append(author)
	return result


def _with_hours(row, user):
	return dict(
		row,
		hours_label=number_label(row.get("hours"), user),
		hours_breakdown_label=hours_breakdown(row.get("hours_details"), user),
	)


def present_email(template_name, context, user):
	"""Extend the common layout while keeping the fields used by saved templates."""
	rows = [_with_hours(row, user) if row.get("timesheet_name") else row for row in context["rows"]]
	timesheet_rows = [row for row in rows if row.get("timesheet_name")]
	is_timesheet = "Timesheet" in template_name or bool(context.get("timesheet_link")) or bool(timesheet_rows)
	if not is_timesheet:
		return dict(is_timesheet=False, author_groups=[], overdue_timesheets=[])

	state = context.get("workflow_state")
	kind = context["email_kind"]
	ungrouped_rows = [row for row in rows if not row.get("timesheet_name")]
	author_groups = timesheet_groups(timesheet_rows, user) if kind != "deadline" else []
	overdue_timesheets = timesheet_deadline_groups(timesheet_rows, user) if kind == "deadline" else []
	count = context["count"]
	if overdue_timesheets:
		count = len(overdue_timesheets) + len({(row.get("doctype"), row.get("name")) for row in ungrouped_rows})
		summary = _("Timesheet") + ": " + str(len(overdue_timesheets))
	elif author_groups:
		sheets = [sheet for author in author_groups for sheet in author["sheets"]]
		summary = " · ".join(
			(
				_("Timesheets") + ": " + str(len(sheets)),
				_("Positions") + ": " + str(sum(sheet["count"] for sheet in sheets)),
				_("Hours") + ": " + number_label(sum(sheet["hours"] for sheet in sheets), user),
			)
		)
	else:
		summary = _("Timesheet") + ": 1"
	if ungrouped_rows and (author_groups or overdue_timesheets):
		summary += " · " + document_summary(ungrouped_rows)
	elif ungrouped_rows:
		summary = document_summary(ungrouped_rows)
	if state and not author_groups:
		summary += " — " + _(state)

	title = context.get("timesheet_title")
	if context.get("timesheet_period_from"):
		title = (
			_("Timesheet")
			+ " · "
			+ date_label(context["timesheet_period_from"], user, date_only=True)
			+ " — "
			+ date_label(context.get("timesheet_period_to"), user, date_only=True)
		)
	hours_label = number_label(context.get("hours"), user)
	hours_breakdown_label = hours_breakdown(context.get("hours_details"), user)
	presentation = dict(
		is_timesheet=True,
		timesheet_title=title,
		hours_label=hours_label,
		hours_breakdown_label=hours_breakdown_label,
		author_groups=author_groups,
		overdue_timesheets=overdue_timesheets,
		subject_document_title=title,
		count=count,
		summary=summary,
		rows=rows,
		ungrouped_rows=ungrouped_rows,
	)
	if author_groups or overdue_timesheets:
		presentation["grouped_rows_template"] = "templates/emails/dinext_timesheet_workflow_grouped_rows.html"
	if kind == "correction":
		presentation.update(
			primary_document_link=context.get("timesheet_link") or context["primary_document_link"],
			primary_document_title=title or context["primary_document_title"],
			document_caption=context.get("position_label"),
		)
	if kind == "action" and "hours" in context:
		presentation["document_details"] = [
			dict(label=_("Hours"), value=hours_label, note=hours_breakdown_label)
		]
	return presentation
