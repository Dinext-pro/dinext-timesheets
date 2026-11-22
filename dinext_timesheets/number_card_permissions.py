"""Narrow read access to public, permission-filtered discipline cards."""

PUBLIC_CARDS = frozenset(
	{
		"On-time Timesheet Submissions",
		"On-time Timesheet Approvals",
		"Overdue Timesheet Approvals",
		"Overdue Timesheet Positions",
		"Timesheet Hours Awaiting Approval",
	}
)


def has_permission(doc, ptype="read", user=None, debug=False):
	if (
		ptype in {"read", "report", "export", "print", "email", "select"}
		and doc.get("is_public")
		and doc.name in PUBLIC_CARDS
	):
		return True
	return None
