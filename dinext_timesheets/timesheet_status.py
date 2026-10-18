"""English status keys and the pure Any/All matcher for timesheet rollup."""

from __future__ import annotations

PARENT_DRAFT = "Draft"
PARENT_PENDING = "Pending Approval"
PARENT_REJECTED = "Rejected"
PARENT_REWORK = "Rework"
PARENT_APPROVED = "Approved"

POSITION_EDITING = "Editing"
POSITION_PENDING = "Pending Approval"
POSITION_APPROVED = "Approved"
POSITION_REJECTED = "Rejected"
POSITION_STATUS_UNSET = "Not Set"

PARENT_STATUSES = (
	PARENT_DRAFT,
	PARENT_PENDING,
	PARENT_REJECTED,
	PARENT_REWORK,
	PARENT_APPROVED,
)

UT_STATUS_FROM_RUSSIAN = {
	"Черновик": PARENT_DRAFT,
	"На согласовании": PARENT_PENDING,
	"Отклонено": PARENT_REJECTED,
	"На доработке": PARENT_REWORK,
	"Согласован": PARENT_APPROVED,
}

UTP_STATUS_FROM_RUSSIAN = {
	"Редактирование": POSITION_EDITING,
	"На согласовании": POSITION_PENDING,
	"Согласовано": POSITION_APPROVED,
	"Отклонено": POSITION_REJECTED,
}

DEFAULT_POSITION_RULES = (
	{
		"position_status": POSITION_REJECTED,
		"timesheet_status": PARENT_REJECTED,
		"threshold": "Any",
	},
	{
		"position_status": POSITION_APPROVED,
		"timesheet_status": PARENT_APPROVED,
		"threshold": "All",
	},
	{
		"position_status": POSITION_EDITING,
		"timesheet_status": PARENT_REWORK,
		"threshold": "Any",
	},
)

DEFAULT_PARENT_RULES = (
	{
		"timesheet_status": PARENT_REWORK,
		"position_status": POSITION_EDITING,
	},
	{
		"timesheet_status": PARENT_PENDING,
		"position_status": POSITION_PENDING,
	},
)

DEFAULT_HIDDEN_LIST_STATUSES = (
	{
		"position_status": POSITION_EDITING,
	},
	{
		"position_status": POSITION_STATUS_UNSET,
	},
)


def first_matching_rule(rules: list[dict], counts: dict[str, int]) -> dict | None:
	"""Return the first rule whose Any/All threshold matches. Empty counts match nothing."""
	total = sum(counts.values())
	for rule in rules:
		status = rule.get("position_status") or ""
		have = counts.get(status, 0)
		if rule.get("threshold") == "Any" and have >= 1:
			return rule
		if rule.get("threshold") == "All" and total > 0 and have == total:
			return rule
	return None
