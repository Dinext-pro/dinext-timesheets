/**
 * Prod V10 picker: Client → Project → Task columns (not in-cell Select).
 * Role is not in this window: first project role is written by default.
 */
import { canEdit } from "../model.js";
import { EMPTY_CLIENT, findProject, listProjects } from "../catalog.js";
import {
	FIELD_PROJECT,
	FIELD_TASK,
	commitCascadePatch,
	ensureCatalog,
} from "./cascade-commit.js";

const PICKER_CLASS = "ut-task-picker";
const CLICK_NS = "click.utTaskPicker";
let _openEl = null;
let _onRoute = null;

export function isTaskPickerOpen() {
	return !!_openEl;
}

export function closeTaskPicker() {
	unbindRoute();
	$(document).off(CLICK_NS);
	_openEl = null;
	document.querySelectorAll(`.${PICKER_CLASS}`).forEach((el) => el.remove());
}

function unbindRoute() {
	if (_onRoute && frappe.router?.off) {
		frappe.router.off("change", _onRoute);
	}
	_onRoute = null;
}

function clientsMap(frm, currentProject) {
	const map = new Map();
	const catalog = listProjects(frm);
	if (currentProject && !catalog.some((project) => project.name === currentProject.name)) {
		catalog.unshift(currentProject);
	}
	for (const source of catalog) {
		const project =
			currentProject?.name === source.name ? currentProject : source;
		const client = project.client || EMPTY_CLIENT;
		if (!map.has(client)) {
			map.set(client, []);
		}
		map.get(client).push(project);
	}
	return map;
}

function findNode(frm, rowId) {
	return frm.ut?.table?.api?.getRowNode?.(String(rowId)) || null;
}

function selectionPatch(project, task, role) {
	return {
		project: project.name,
		project_label: project.project_name || project.name,
		document_type: task.tsdoctype || "Task",
		document_name: task.name,
		document_label: task.subject || task.name,
		project_role: role,
	};
}

function currentProjectForPicker(frm, row) {
	const found = findProject(frm, row.project);
	if (!found && !row.project) {
		return null;
	}
	const project = found
		? { ...found, tasks_issues: [...(found.tasks_issues || [])] }
		: {
				name: row.project,
				project_name: row.project_label || row.project,
				tasks_issues: [],
				roles: row.project_role ? [row.project_role] : [],
				client: EMPTY_CLIENT,
			};
	if (
		row.document_name &&
		!project.tasks_issues.some((task) => task.name === row.document_name)
	) {
		project.tasks_issues.unshift({
			name: row.document_name,
			subject: row.document_label || row.document_name,
			tsdoctype: row.document_type || "Task",
			level: 0,
		});
	}
	return project;
}

function placePicker(el, anchorEl) {
	const margin = 8;
	const rect = anchorEl?.getBoundingClientRect?.();
	const top = rect ? rect.bottom + 4 : 120;
	const left = rect ? rect.left : 120;
	requestAnimationFrame(() => {
		const box = el.getBoundingClientRect();
		el.style.top = `${Math.max(
			margin,
			Math.min(top, window.innerHeight - box.height - margin)
		)}px`;
		el.style.left = `${Math.max(
			margin,
			Math.min(left, window.innerWidth - box.width - margin)
		)}px`;
	});
}

function makeColumn(title, { search = false, wide = false } = {}) {
	const $col = $(
		`<div class="ut-task-picker__col${wide ? " ut-task-picker__col--wide" : ""}"></div>`
	);
	$col.append(`<div class="ut-task-picker__head">${frappe.utils.escape_html(title)}</div>`);
	let $search = null;
	if (search) {
		$search = $(
			`<input type="search" class="ut-task-picker__search form-control" placeholder="${__(
				"Поиск"
			)}" autocomplete="off">`
		);
		$col.append($search);
	}
	const $body = $('<div class="ut-task-picker__body" role="listbox"></div>');
	$col.append($body);
	return { $col, $body, $search };
}

function selectedValue($body) {
	return $body.find(".ut-task-picker__item--selected").attr("data-value") || "";
}

function fillList($body, items, selected) {
	$body.empty();
	if (!items.length) {
		$body.append(
			`<div class="ut-task-picker__empty">${__("Нет вариантов")}</div>`
		);
		return;
	}
	for (const item of items) {
		const $btn = $(
			'<button type="button" class="ut-task-picker__item"></button>'
		);
		$btn.attr("data-value", item.value);
		$btn.attr("tabindex", "-1");
		$btn.attr("title", item.label);
		$btn.text(item.label);
		const level = cint(item.level);
		if (level > 0) {
			$btn.css("padding-left", `${10 + level * 12}px`);
		}
		if (item.value === selected) {
			$btn.addClass("ut-task-picker__item--selected");
		}
		$body.append($btn);
	}
}

function listItems($body) {
	return $body.find(".ut-task-picker__item").toArray();
}

function selectItemEl($body, el, onChange) {
	if (!el) {
		return;
	}
	const value = String($(el).attr("data-value") || "");
	const changed = selectedValue($body) !== value;
	$body.find(".ut-task-picker__item--selected").removeClass(
		"ut-task-picker__item--selected"
	);
	$(el).addClass("ut-task-picker__item--selected");
	el.scrollIntoView?.({ block: "nearest" });
	if (changed) {
		onChange?.(value);
	}
}

function moveInList($body, delta, onChange) {
	const els = listItems($body);
	if (!els.length) {
		return;
	}
	let idx = els.findIndex((el) =>
		el.classList.contains("ut-task-picker__item--selected")
	);
	if (idx < 0) {
		idx = delta > 0 ? 0 : els.length - 1;
	} else {
		const next = Math.max(0, Math.min(els.length - 1, idx + delta));
		if (next === idx) {
			return;
		}
		idx = next;
	}
	selectItemEl($body, els[idx], onChange);
}

function taskMatches(task, query) {
	if (!query) {
		return true;
	}
	const q = query.toLowerCase();
	const subject = String(task.subject || "").toLowerCase();
	const name = String(task.name || "").toLowerCase();
	return subject.includes(q) || name.includes(q);
}

/**
 * @param {object} frm
 * @param {{ node?: object, data?: object, event?: object, field?: string, anchor?: Element }} opts
 */
export function openTaskPicker(frm, opts = {}) {
	if (!canEdit(frm) || !ensureCatalog(frm)) {
		return;
	}
	const node = opts.node || findNode(frm, opts.data?.id);
	const row = node?.data || opts.data;
	if (!row || row.rowType !== "position") {
		return;
	}

	closeTaskPicker();

	const currentProject = currentProjectForPicker(frm, row);
	const byClient = clientsMap(frm, currentProject);
	if (!byClient.size) {
		frappe.msgprint(__("Нет доступных проектов"));
		return;
	}

	const el = document.createElement("div");
	el.className = PICKER_CLASS;
	el.setAttribute("role", "dialog");
	el.setAttribute("aria-label", __("Выбор задачи"));

	const $el = $(el);
	const $cols = $('<div class="ut-task-picker__cols"></div>').appendTo($el);
	const clientCol = makeColumn(__("Клиент"));
	const projectCol = makeColumn(__("Проект"));
	const taskCol = makeColumn(__("Задача"), { search: true, wide: true });
	clientCol.$col.appendTo($cols);
	projectCol.$col.appendTo($cols);
	taskCol.$col.appendTo($cols);

	const $actions = $('<div class="ut-task-picker__actions"></div>').appendTo($el);
	const $cancel = $(
		`<button type="button" class="btn btn-default btn-sm">${__("Отмена")}</button>`
	).appendTo($actions);
	const $select = $(
		`<button type="button" class="btn btn-primary btn-sm">${__("Выбрать")}</button>`
	).appendTo($actions);

	let projects = [];
	let draftProject = currentProject;
	let draftTask =
		currentProject?.tasks_issues?.find((task) => task.name === row.document_name) ||
		null;

	function renderTasks(project) {
		const query = String(taskCol.$search?.val?.() || "").trim();
		const tasks = (project?.tasks_issues || []).filter((t) =>
			taskMatches(t, query)
		);
		if (!tasks.length) {
			taskCol.$body.empty().append(
				`<div class="ut-task-picker__empty">${
					query ? __("Ничего не найдено") : __("Нет задач")
				}</div>`
			);
			return;
		}
		fillList(
			taskCol.$body,
			tasks.map((t) => ({
				label: t.subject || t.name,
				value: t.name,
				level: t.level,
			})),
			draftTask?.name
		);
	}

	function onClientChange(client) {
		projects = byClient.get(client) || [];
		draftProject = null;
		draftTask = null;
		fillList(
			projectCol.$body,
			projects.map((p) => ({ label: p.project_name || p.name, value: p.name }))
		);
		taskCol.$search?.val?.("");
		taskCol.$body.empty();
	}

	function onProjectChange(name) {
		const project = projects.find((p) => p.name === name);
		if (!project) {
			return;
		}
		if (draftProject?.name !== project.name) {
			draftTask = null;
			taskCol.$search?.val?.("");
		}
		draftProject = project;
		renderTasks(project);
	}

	function onTaskChange(name) {
		draftTask =
			(draftProject?.tasks_issues || []).find((task) => task.name === name) ||
			null;
	}

	function confirmTask() {
		if (!draftProject || !draftTask) {
			return;
		}
		const live = findNode(frm, row.id);
		if (!live) {
			dismiss();
			return;
		}
		const role =
			draftProject.name === live.data?.project
				? live.data?.project_role || draftProject.roles?.[0] || ""
				: draftProject.roles?.[0] || "";
		commitCascadePatch(
			frm,
			{ node: live, data: live.data, api: frm.ut?.table?.api },
			selectionPatch(draftProject, draftTask, role)
		);
		dismiss();
	}

	fillList(
		clientCol.$body,
		[...byClient.keys()].map((client) => ({ label: client, value: client })),
		currentProject?.client || [...byClient.keys()][0]
	);

	const startClient = selectedValue(clientCol.$body);
	if (startClient) {
		projects = byClient.get(startClient) || [];
		fillList(
			projectCol.$body,
			projects.map((p) => ({ label: p.project_name || p.name, value: p.name })),
			currentProject?.name
		);
		if (currentProject) {
			renderTasks(currentProject);
		}
	}

	const panes = [
		{ $body: clientCol.$body, onChange: onClientChange },
		{ $body: projectCol.$body, onChange: onProjectChange },
		{ $body: taskCol.$body, onChange: onTaskChange },
	];
	const TAB_LAST = 4;
	const openField =
		opts.field ||
		opts.event?.colDef?.field ||
		opts.event?.column?.getColId?.() ||
		FIELD_PROJECT;
	let paneIdx = 0;
	if (currentProject) {
		paneIdx = openField === FIELD_TASK ? 2 : 1;
	}

	function restoreGridFocus() {
		const api = frm.ut?.table?.api;
		const rowIndex = node?.rowIndex ?? opts.event?.node?.rowIndex;
		if (!api || rowIndex == null) {
			return;
		}
		requestAnimationFrame(() => {
			api.setFocusedCell?.(rowIndex, openField);
		});
	}

	function dismiss() {
		closeTaskPicker();
		restoreGridFocus();
	}

	function caretItem($body) {
		return (
			$body.find(".ut-task-picker__item--selected").get(0) ||
			listItems($body)[0] ||
			null
		);
	}

	function focusCaret() {
		const item = caretItem(panes[paneIdx].$body);
		if (item) {
			item.focus({ preventScroll: true });
			item.scrollIntoView?.({ block: "nearest" });
			return;
		}
		if (paneIdx === 2) {
			taskCol.$search?.trigger?.("focus");
		}
	}

	function setCaret(idx) {
		paneIdx = Math.max(0, Math.min(2, idx));
		const pane = panes[paneIdx];
		if (!selectedValue(pane.$body)) {
			moveInList(pane.$body, 1, pane.onChange);
		}
		focusCaret();
	}

	function applyTab(delta, target) {
		let current = paneIdx;
		if (target === $select.get(0)) {
			current = 3;
		} else if (target === $cancel.get(0)) {
			current = 4;
		}
		const next = ((current + delta) % (TAB_LAST + 1) + (TAB_LAST + 1)) %
			(TAB_LAST + 1);
		if (next <= 2) {
			setCaret(next);
			return;
		}
		if (next === 3) {
			$select.trigger("focus");
			return;
		}
		$cancel.trigger("focus");
	}

	function onEnter() {
		if (paneIdx >= 2) {
			if (!selectedValue(taskCol.$body)) {
				moveInList(taskCol.$body, 1, onTaskChange);
			}
			confirmTask();
			return;
		}
		setCaret(paneIdx + 1);
	}

	panes.forEach((pane, idx) => {
		pane.$body.on("click", ".ut-task-picker__item", function () {
			selectItemEl(pane.$body, this, pane.onChange);
			setCaret(idx);
		});
	});
	taskCol.$body.on("dblclick", ".ut-task-picker__item", confirmTask);
	taskCol.$search?.on?.("input", () => {
		renderTasks(draftProject);
	});
	taskCol.$search?.on?.("focus", () => {
		paneIdx = 2;
	});
	$select.on("click", confirmTask);
	$cancel.on("click", dismiss);

	el.addEventListener("keydown", (e) => {
		const searchEl = taskCol.$search?.get?.(0);
		const inSearch = e.target === searchEl;
		const inAction = e.target === $select.get(0) || e.target === $cancel.get(0);
		if (e.key === "Escape") {
			e.preventDefault();
			e.stopPropagation();
			if (inSearch && String(taskCol.$search.val() || "").trim()) {
				taskCol.$search.val("");
				renderTasks(draftProject);
				return;
			}
			dismiss();
			return;
		}
		if (e.key === "Tab") {
			e.preventDefault();
			e.stopPropagation();
			applyTab(e.shiftKey ? -1 : 1, e.target);
			return;
		}
		if (e.key === "Enter") {
			if (e.target === $select.get(0) || e.target === $cancel.get(0)) {
				return;
			}
			e.preventDefault();
			e.stopPropagation();
			onEnter();
			return;
		}
		if (e.key === "ArrowDown" || e.key === "ArrowUp") {
			if (inAction) {
				return;
			}
			e.preventDefault();
			e.stopPropagation();
			if (inSearch) {
				paneIdx = 2;
			}
			const pane = panes[paneIdx];
			moveInList(pane.$body, e.key === "ArrowDown" ? 1 : -1, pane.onChange);
			focusCaret();
			return;
		}
		if (e.key === "ArrowLeft" && inSearch) {
			if (searchEl.selectionStart === 0 && searchEl.selectionEnd === 0) {
				e.preventDefault();
				e.stopPropagation();
				setCaret(1);
			}
			return;
		}
		if (
			(e.key === "ArrowRight" || e.key === "ArrowLeft") &&
			!inSearch &&
			!inAction
		) {
			e.preventDefault();
			e.stopPropagation();
			setCaret(paneIdx + (e.key === "ArrowRight" ? 1 : -1));
		}
	});

	document.body.appendChild(el);
	_openEl = el;
	requestAnimationFrame(() => {
		el.classList.add("ut-task-picker--open");
		focusCaret();
	});

	const anchor =
		opts.anchor ||
		opts.event?.event?.target ||
		opts.event?.target ||
		frm.ut?.container;
	placePicker(el, anchor);

	_onRoute = closeTaskPicker;
	frappe.router?.on?.("change", _onRoute);

	setTimeout(() => {
		$(document).on(CLICK_NS, (e) => {
			if ($(e.target).closest(`.${PICKER_CLASS}`).length) {
				return;
			}
			dismiss();
		});
	}, 0);
}
