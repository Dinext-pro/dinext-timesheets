/** Customer → project → task catalog from get_timesheet_tasks (remap2). */

/** Empty Project.customer (0..1 Link) → internal/presale bucket. */
export const EMPTY_CLIENT = __("No Client");

function normalizeClient(label) {
	const s = String(label || "").trim();
	return s || EMPTY_CLIENT;
}

/** Tree is [{ "Client": [projects] }, ...] or { Client: [projects] }. */
function forEachClientProjects(frm, fn) {
	const raw = frm.ut?.tasksData || frm.tasks_data;
	if (!raw || typeof raw !== "object") {
		return;
	}
	const blocks = Array.isArray(raw) ? raw : [raw];
	for (const block of blocks) {
		if (!block || typeof block !== "object" || Array.isArray(block)) {
			continue;
		}
		for (const [clientLabel, projects] of Object.entries(block)) {
			if (!Array.isArray(projects)) {
				continue;
			}
			fn(normalizeClient(clientLabel), projects);
		}
	}
}

/**
 * @param {string} [clientLabel] filter by Project.customer bucket
 * @returns {Array<{name: string, project_name: string, tasks_issues: any[], roles: string[], client: string}>}
 */
export function listProjects(frm, clientLabel) {
	const want = clientLabel ? normalizeClient(clientLabel) : "";
	const out = [];
	const seen = new Set();
	forEachClientProjects(frm, (client, projects) => {
		if (want && client !== want) {
			return;
		}
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
				client,
			});
		}
	});
	return out;
}

export function taskLabelFromCatalog(frm, documentName) {
	if (!documentName) {
		return "";
	}
	for (const p of listProjects(frm)) {
		const t = (p.tasks_issues || []).find((x) => x.name === documentName);
		if (t) {
			return t.subject || t.name;
		}
	}
	return "";
}

export function projectLabelFromCatalog(frm, projectName) {
	const p = findProject(frm, projectName);
	return p?.project_name || "";
}

export function findProject(frm, projectName) {
	if (!projectName) {
		return null;
	}
	return listProjects(frm).find((p) => p.name === projectName) || null;
}

/** V10: autofill role only when the project has exactly one. */
export function defaultRoleForProject(project) {
	const roles = project?.roles || [];
	return roles.length === 1 ? roles[0] : "";
}

/** Roles for the row project. Keep current value selectable if catalog dropped it. */
export function roleOptionsForRow(frm, row) {
	const project = findProject(frm, row?.project);
	const roles = [...(project?.roles || [])];
	if (row?.project_role && !roles.includes(row.project_role)) {
		roles.unshift(row.project_role);
	}
	return roles;
}
