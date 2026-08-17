/** Flat project/task catalog from get_timesheet_tasks payload. */

const SEP = " · ";

function safeLevel(level) {
	const n = cint(level);
	return Number.isFinite(n) && n > 0 ? n : 0;
}

/** @returns {Array<{name: string, project_name: string, tasks_issues: any[], roles: string[], client?: string}>} */
export function listProjects(frm) {
	const customers = frm.ut?.tasksData || frm.tasks_data;
	if (!customers || typeof customers !== "object") {
		return [];
	}
	const out = [];
	const seen = new Set();
	Object.values(customers).forEach((clientObj) => {
		if (!clientObj || typeof clientObj !== "object") {
			return;
		}
		Object.entries(clientObj).forEach(([clientLabel, projects]) => {
			for (const p of projects || []) {
				if (!p?.name || seen.has(p.name)) {
					continue;
				}
				seen.add(p.name);
				out.push({
					name: p.name,
					project_name: p.project_name || p.name,
					tasks_issues: p.tasks_issues || [],
					roles: p.roles || [],
					client: clientLabel,
				});
			}
		});
	});
	return out;
}

export function findProject(frm, projectName) {
	if (!projectName) {
		return null;
	}
	return listProjects(frm).find((p) => p.name === projectName) || null;
}

export function parseOptionName(optionLabel) {
	if (!optionLabel) {
		return "";
	}
	const idx = String(optionLabel).lastIndexOf(SEP);
	if (idx >= 0) {
		return String(optionLabel).slice(idx + SEP.length).trim();
	}
	return "";
}

/**
 * Frappe Select has no separate label/value — option text is the value.
 * Prefer human label; append " · name" only when label collides.
 */
export function buildProjectSelectOptions(projects) {
	const counts = {};
	for (const p of projects) {
		const label = p.project_name || p.name;
		counts[label] = (counts[label] || 0) + 1;
	}
	return projects.map((p) => {
		const label = p.project_name || p.name;
		const option = counts[label] > 1 ? `${label}${SEP}${p.name}` : label;
		return { option, project: p };
	});
}

export function buildTaskSelectOptions(tasks) {
	const counts = {};
	for (const t of tasks) {
		const label = t.subject || t.name;
		counts[label] = (counts[label] || 0) + 1;
	}
	return tasks.map((t) => {
		const indent = " ".repeat(safeLevel(t.level));
		const label = t.subject || t.name;
		const option =
			counts[label] > 1
				? `${indent}${label}${SEP}${t.name}`
				: `${indent}${label}`;
		return { option, task: t };
	});
}

export function resolveProjectOption(projects, selected) {
	if (!selected) {
		return null;
	}
	const byId = parseOptionName(selected);
	if (byId) {
		return projects.find((p) => p.name === byId) || null;
	}
	const exactId = projects.find((p) => p.name === selected);
	if (exactId) {
		return exactId;
	}
	const byLabel = projects.filter(
		(p) => (p.project_name || p.name) === selected
	);
	return byLabel.length === 1 ? byLabel[0] : null;
}

export function resolveTaskOption(tasks, selected) {
	if (!selected) {
		return null;
	}
	const byId = parseOptionName(selected);
	if (byId) {
		return tasks.find((t) => t.name === byId) || null;
	}
	const trimmed = String(selected).trim();
	const exactId = tasks.find((t) => t.name === trimmed);
	if (exactId) {
		return exactId;
	}
	const byLabel = tasks.filter((t) => (t.subject || t.name) === trimmed);
	return byLabel.length === 1 ? byLabel[0] : null;
}

/** Ensure current row value stays selectable even if not in catalog. */
export function projectOptionsForRow(frm, row) {
	const projects = listProjects(frm);
	if (row?.project && !projects.some((p) => p.name === row.project)) {
		projects.unshift({
			name: row.project,
			project_name: row.project_label || row.project,
			tasks_issues: [],
			roles: row.project_role ? [row.project_role] : [],
		});
	}
	return projects;
}

export function taskOptionsForRow(frm, row) {
	const project = findProject(frm, row?.project);
	const tasks = [...(project?.tasks_issues || [])];
	if (
		row?.document_name &&
		!tasks.some((t) => t.name === row.document_name)
	) {
		tasks.unshift({
			name: row.document_name,
			subject: row.document_label || row.document_name,
			tsdoctype: row.document_type || "Task",
			level: 0,
		});
	}
	return tasks;
}

export function roleOptionsForRow(frm, row) {
	const project = findProject(frm, row?.project);
	const roles = [...(project?.roles || [])];
	if (row?.project_role && !roles.includes(row.project_role)) {
		roles.unshift(row.project_role);
	}
	return roles;
}
