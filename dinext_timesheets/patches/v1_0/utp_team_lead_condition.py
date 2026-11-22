"""Preserve eligibility when migrating an existing UTP Team Lead condition."""

import ast

import frappe


OLD_ROLE = "Z_Dinord_Team_Lead"
NEW_ROLE = "Dinext_Team_Lead"
# The legacy query has no parenttype filter. Its result is used as a boolean.
_ROLE_LOOKUP = ast.dump(ast.parse(
	'frappe.db.get_value("Has Role", {"parent": frappe.session.user, "role": "Z_Dinord_Team_Lead"}, "role")',
	mode="eval",
).body)


def migrate_condition(condition):
	if not condition or condition.count(OLD_ROLE) != 1:
		return condition
	try:
		root = ast.parse(condition.strip(), mode="eval")
	except SyntaxError:
		return condition

	# Follow only branches whose truth value determines the condition. A comparison
	# against the returned role name can change even when both roles have the same members.
	branches = [root.body]
	while branches:
		node = branches.pop()
		if isinstance(node, ast.BoolOp):
			branches.extend(node.values)
		elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
			branches.append(node.operand)
		elif isinstance(node, ast.Call) and ast.dump(node) == _ROLE_LOOKUP:
			members = {OLD_ROLE: set(), NEW_ROLE: set()}
			for row in frappe.get_all(
				"Has Role", filters={"role": ("in", [OLD_ROLE, NEW_ROLE])}, fields=["parent", "role"],
			):
				members[row.role].add(row.parent)
			if members[OLD_ROLE] == members[NEW_ROLE]:
				return condition.replace(OLD_ROLE, NEW_ROLE)
	return condition
