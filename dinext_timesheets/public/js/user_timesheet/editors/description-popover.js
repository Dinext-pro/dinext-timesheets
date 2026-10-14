import { canEdit, dayField, descField, sumDayHours, syncPositionFromRow } from "../model.js";
import { buildSummaryRows } from "../summary.js";
import { scheduleRefreshLimits } from "../limits.js";
import { clearInvalidAfterEdit, clearInvalidFields } from "../invalid-cells.js";

const POPOVER_NS = ".utDescrPopover";
const POPOVER_SEL = ".ut-descr-popover";
const POPOVER_WIDTH = 252;

let hoverCloseTimer = null;

function cancelHoverClose() {
	if (hoverCloseTimer) {
		clearTimeout(hoverCloseTimer);
		hoverCloseTimer = null;
	}
}

function scheduleHoverClose() {
	cancelHoverClose();
	hoverCloseTimer = setTimeout(() => {
		hoverCloseTimer = null;
		closeDescriptionPopover();
	}, 180);
}

function isClosedStatus(frm) {
	return ["Pending Approval", "Approved", "Rejected"].includes(frm.doc?.ut_status);
}

/**
 * Description edit only while the grid is editable.
 * Read-only TS (approval / approved / rejected): textarea locked, hover to read.
 */
function isDescriptionReadonly(frm) {
	return !canEdit(frm);
}

function lockDescriptionTextarea($ta, locked) {
	$ta.prop({ disabled: locked, readOnly: locked });
	$ta.attr("aria-readonly", locked ? "true" : "false");
	if (locked) {
		$ta.off("input.utLock keydown.utLock beforeinput.utLock");
		$ta.on("beforeinput.utLock", (e) => e.preventDefault());
		$ta.on("keydown.utLock", (e) => {
			if (e.key === "Escape" || e.key === "Tab") {
				return;
			}
			if (e.ctrlKey || e.metaKey) {
				return;
			}
			e.preventDefault();
		});
	} else {
		$ta.off(".utLock");
	}
}

/** ±hours only outside closed statuses — Full_Access does not unlock hours. */
function canEditHoursInPopover(frm) {
	return !isClosedStatus(frm);
}

function fmtHours(value) {
	const n = flt(value) || 0;
	return Number.isInteger(n) ? String(n) : String(Math.round(n * 10) / 10);
}

function hoursLabel(row, date) {
	return `${fmtHours(row[dayField(date)])} ${__("h")}`;
}

export function closeDescriptionPopover() {
	cancelHoverClose();
	$(document).off(POPOVER_NS);
	$(window).off(POPOVER_NS);
	$(POPOVER_SEL).remove();
}

function focusColId(column) {
	if (column == null) {
		return "";
	}
	if (typeof column === "string") {
		return column;
	}
	if (typeof column.getColId === "function") {
		return column.getColId();
	}
	return "";
}

/** Live focused day cell — AG Grid marks it with .ag-cell-focus after navigation. */
function focusedDayCellEl(api) {
	const gui = api?.getGui?.();
	const root = gui || document.querySelector(".user-timesheet-table");
	if (!root) {
		return null;
	}
	const summaryFocus = root.querySelector(
		".dinext-table-row--summary .ag-cell-focus, .ag-floating-bottom .ag-cell-focus, .ag-pinned-left-floating-bottom .ag-cell-focus, .ag-pinned-right-floating-bottom .ag-cell-focus"
	);
	if (summaryFocus) {
		return summaryFocus;
	}
	return root.querySelector(".ag-cell-focus");
}

function resolveFocusNode(api, event) {
	if (event?.node?.data) {
		return event.node;
	}
	if (event?.rowPinned === "bottom") {
		return api.getPinnedBottomRow?.(event.rowIndex) || null;
	}
	if (event?.rowPinned === "top") {
		return api.getPinnedTopRow?.(event.rowIndex) || null;
	}
	return api.getDisplayedRowAtIndex?.(event.rowIndex) || null;
}

/** Pinned summary reports rowIndex 0 — same as first body row. */
function isSummaryFocus(event, node, row, cellEl) {
	if (event?.rowPinned === "bottom" || event?.rowPinned === "top") {
		return true;
	}
	if (node?.rowPinned === "bottom" || node?.rowPinned === "top") {
		return true;
	}
	if (event?.node?.rowPinned === "bottom" || event?.node?.rowPinned === "top") {
		return true;
	}
	if (row?.id === "ut_day_totals") {
		return true;
	}
	if (row?._section === "summary" || row?.section === "summary") {
		return true;
	}
	if (
		cellEl?.closest?.(
			".dinext-table-row--summary, .ag-floating-bottom, .ag-pinned-left-floating-bottom, .ag-pinned-right-floating-bottom"
		)
	) {
		return true;
	}
	return false;
}

function resolveAnchorEl(api, anchor) {
	if (anchor?.jquery) {
		anchor = anchor[0];
	}
	if (anchor?.getBoundingClientRect) {
		return anchor;
	}
	return focusedDayCellEl(api);
}

/** Hovered day cell — do not fall back to focused cell (readonly hover). */
function hoverCellEl(event) {
	const fromDom = event?.event?.target?.closest?.(".ag-cell");
	if (fromDom?.getBoundingClientRect) {
		return fromDom;
	}
	if (event?.eGridCell?.getBoundingClientRect) {
		return event.eGridCell;
	}
	return null;
}

function placePopover($popover, anchor) {
	const el = resolveAnchorEl(null, anchor);
	if (!el?.getBoundingClientRect) {
		return false;
	}
	const rect = el.getBoundingClientRect();
	const gap = 10;
	const width = POPOVER_WIDTH;
	const mh = $popover.outerHeight() || 160;
	let placement = "below";
	let top = rect.bottom + gap;
	let left = rect.left + rect.width / 2 - width / 2;

	if (top + mh > window.innerHeight - 8) {
		placement = "above";
		top = Math.max(8, rect.top - mh - gap);
	}
	left = Math.max(8, Math.min(left, window.innerWidth - width - 8));

	const caretX = rect.left + rect.width / 2 - left;
	$popover
		.toggleClass("ut-descr-popover--below", placement === "below")
		.toggleClass("ut-descr-popover--above", placement === "above")
		.css({
			top: `${top}px`,
			left: `${left}px`,
			"--caret-left": `${Math.max(14, Math.min(width - 14, caretX))}px`,
		});
	return true;
}

function focusDayCell(frm, row, date) {
	const api = frm.ut?.table?.api;
	const node = api?.getRowNode?.(String(row.id));
	if (!api || node?.rowIndex == null) {
		return;
	}
	const field = dayField(date);
	api.ensureColumnVisible?.(field);
	api.setFocusedCell?.(node.rowIndex, field);
}

function persistHours(frm, row, date) {
	const hoursField = dayField(date);
	row.total = sumDayHours(row, frm.ut?.dates || []);
	syncPositionFromRow(frm, row);
	frm.ut.summaryRows = buildSummaryRows(frm);
	frm.ut.table?.setSummaryRows?.(frm.ut.summaryRows);
	/* Cancel in-cell edit so refresh is not fighting the editor. */
	frm.ut.table?.api?.stopEditing?.(false);
	const node = frm.ut.table?.api?.getRowNode?.(String(row.id));
	frm.ut.table?.api?.refreshCells?.({
		rowNodes: node ? [node] : undefined,
		columns: [hoursField, "total"],
		force: true,
	});
	scheduleRefreshLimits(frm);
	frm.dirty();
	clearInvalidAfterEdit(frm, row.id, hoursField);
	focusDayCell(frm, row, date);
}

function applyHoursDelta(frm, row, date, delta, $hoursLabel) {
	const hoursField = dayField(date);
	row[hoursField] = Math.max((flt(row[hoursField]) || 0) + delta, 0);
	$hoursLabel?.text(hoursLabel(row, date));
	persistHours(frm, row, date);
}

function bindOutsideClose($popover, $anchor, hoursField) {
	$(document).off(POPOVER_NS);
	$(window).off(POPOVER_NS);

	$(document).on(`mousedown${POPOVER_NS}`, (e) => {
		const t = e.target;
		if ($(t).closest(POPOVER_SEL).length) {
			return;
		}
		if ($anchor.length && ($(t).closest($anchor).length || $anchor.is(t))) {
			return;
		}
		if ($(t).closest(".ag-cell-inline-editing").length) {
			const col = $(t).closest(".ag-cell").attr("col-id");
			if (col === hoursField) {
				return;
			}
		}
		/* Day cell of this popover (not only editing). */
		if ($(t).closest(`.ag-cell[col-id="${hoursField}"]`).length) {
			return;
		}
		closeDescriptionPopover();
	});
	$(document).on(`keydown${POPOVER_NS}`, (e) => {
		if (e.key !== "Escape") {
			return;
		}
		const inPopover = $(e.target).closest(POPOVER_SEL).length;
		if (inPopover) {
			e.preventDefault();
			e.stopPropagation();
			const ctx = $popover.data("utCtx");
			if (ctx) {
				focusDayCell(ctx.frm, ctx.row, ctx.date);
			}
			/* Esc from textarea → back to cell, popover stays (demodev companion). */
			return;
		}
		closeDescriptionPopover();
	});
	$(window).on(`resize${POPOVER_NS} scroll${POPOVER_NS}`, () => {
		const anchor = $popover.data("utAnchor");
		if ($(POPOVER_SEL).length && anchor) {
			placePopover($(POPOVER_SEL), anchor);
		}
	});
}

/**
 * Companion popover (demodev): does not steal focus from the hours cell.
 * Type hours in cell; click textarea or Alt+↓ / F2 for comment.
 */
export function openDescriptionPopover(frm, row, date, anchor) {
	if (!row || row.rowType !== "position" || !date) {
		return;
	}

	const api = frm.ut?.table?.api;
	const hoursField = dayField(date);
	const descriptionKey = descField(date);
	const anchorEl = resolveAnchorEl(api, anchor);
	if (!anchorEl) return;
	
	const $anchor = $(anchorEl);
	const $existing = $(POPOVER_SEL);

	/* Existing popover — sync content + move to the new cell. */
	if ($existing.length) {
		$existing.data({
			utOpenedAt: Date.now(),
			utRowId: String(row.id),
			utDate: date,
			utAnchor: anchorEl,
			utCtx: { frm, row, date },
		});
		$existing.find(".ut-descr-popover__hours").text(hoursLabel(row, date));
		const $ta = $existing.find(".ut-descr-popover__input");
		lockDescriptionTextarea($ta, isDescriptionReadonly(frm));
		if (!$ta.is(":focus")) {
			$ta.val(row[descriptionKey] || "");
		}
		placePopover($existing, anchorEl);
		bindOutsideClose($existing, $anchor, hoursField);
		return;
	}

	closeDescriptionPopover();

	const descReadonly = isDescriptionReadonly(frm);
	const hoursEditable = canEditHoursInPopover(frm);
	const label = hoursLabel(row, date);

	const $popover = $(`
		<div class="ut-descr-popover" role="dialog" aria-label="${__("Description")}">
			<div class="ut-descr-popover__caret" aria-hidden="true"></div>
			<textarea class="form-control ut-descr-popover__input" rows="3" placeholder="${__(
				"What was done"
			)}"></textarea>
			<div class="ut-descr-popover__foot">
				<div class="ut-descr-popover__stepper"></div>
			</div>
		</div>
	`);
	const $textarea = $popover.find(".ut-descr-popover__input").val(row[descriptionKey] || "");
	const $stepper = $popover.find(".ut-descr-popover__stepper");

	lockDescriptionTextarea($textarea, descReadonly);
	if (!descReadonly) {
		$textarea.on("input", () => {
			row[descriptionKey] = String($textarea.val() || "");
			syncPositionFromRow(frm, row);
			if (String($textarea.val() || "").trim()) {
				clearInvalidFields(frm, row.id, [dayField(date)]);
			}
			frm.dirty();
		});
		$textarea.on("keydown", (e) => {
			if (e.key === "Escape") {
				e.preventDefault();
				e.stopPropagation();
				focusDayCell(frm, row, date);
			} else if (e.key === "Tab" && !e.shiftKey) {
				e.preventDefault();
				focusDayCell(frm, row, date);
			}
		});
	}

	if (hoursEditable) {
		$stepper.html(`
			<button type="button" class="ut-descr-popover__step ut-hrs-decr" tabindex="-1" title="-30 ${__(
				"min"
			)}" aria-label="-30 ${__("min")}">−</button>
			<span class="ut-descr-popover__hours">${frappe.utils.escape_html(label)}</span>
			<button type="button" class="ut-descr-popover__step ut-hrs-incr" tabindex="-1" title="+30 ${__(
				"min"
			)}" aria-label="+30 ${__("min")}">+</button>
		`);
		const $hoursLabel = $stepper.find(".ut-descr-popover__hours");
		/* Keep focus out of stepper — hours stay in the grid cell. */
		$stepper.on("mousedown", ".ut-descr-popover__step", (e) => e.preventDefault());
		$stepper.on("click", ".ut-hrs-incr", (e) => {
			e.preventDefault();
			applyHoursDelta(frm, row, date, 0.5, $hoursLabel);
		});
		$stepper.on("click", ".ut-hrs-decr", (e) => {
			e.preventDefault();
			applyHoursDelta(frm, row, date, -0.5, $hoursLabel);
		});
	} else {
		$stepper.html(
			`<span class="ut-descr-popover__hours">${frappe.utils.escape_html(label)}</span>`
		);
	}

	$popover.data({
		utOpenedAt: Date.now(),
		utRowId: String(row.id),
		utDate: date,
		utAnchor: anchorEl,
		utCtx: { frm, row, date },
	});

	$popover.on("mouseenter", cancelHoverClose);
	$popover.on("mouseleave", () => {
		if (!canEdit(frm)) {
			scheduleHoverClose();
		}
	});

	$("body").append($popover);
	placePopover($popover, anchorEl);
	/* No autofocus — demodev: hours input keeps focus, comment is companion. */
	setTimeout(() => bindOutsideClose($popover, $anchor, hoursField), 0);
}

export function focusDescriptionTextarea() {
	const $ta = $(POPOVER_SEL).find(".ut-descr-popover__input");
	if ($ta.length && !$ta.prop("disabled")) {
		$ta.trigger("focus");
		return true;
	}
	return false;
}

/**
 * demodev: hours focus opens comment companion.
 * Wired via gridOptions.onCellFocused → DinextTable mergeGridOptions/chainHandlers
 * (alongside selection + fillHandle).
 */
export function handleDayDescrCellFocused(frm, event) {
	/* Gesture flag is set in capture mousedown, before this focus event. */
	if (frm?.ut?._descrPointerGesture || frm?.ut?.table?._isFillDragging) {
		closeDescriptionPopover();
		return;
	}

	const api = frm.ut?.table?.api;
	if (!api || event?.rowIndex == null) {
		return;
	}

	const node = resolveFocusNode(api, event);
	const row = node?.data;
	const cellEl = focusedDayCellEl(api);
	if (isSummaryFocus(event, node, row, cellEl)) {
		closeDescriptionPopover();
		return;
	}

	const field = focusColId(event.column);
	if (!field.startsWith("day_")) {
		if (!$(document.activeElement).closest(POPOVER_SEL).length) {
			closeDescriptionPopover();
		}
		return;
	}

	if (!row || row.rowType !== "position") {
		closeDescriptionPopover();
		return;
	}

	const date = field.slice("day_".length);
	const rowId = String(row.id);
	/*
	 * Selection mixin collapses a range on this same cellFocused, but its handler
	 * is chained after ours. Decide after it has updated cellRanges.
	 */
	setTimeout(() => {
		if (!frm.ut || frm.ut._descrPointerGesture || frm.ut.table?._isFillDragging) {
			return;
		}
		if (isMultiCellSelection(frm.ut.table)) {
			closeDescriptionPopover();
			return;
		}
		const ctx = focusedDayContext(frm);
		if (!ctx || ctx.date !== date || String(ctx.row.id) !== rowId) {
			return;
		}
		openDescriptionPopover(frm, ctx.row, ctx.date, ctx.cellEl);
	}, 0);
}

/** Read-only: hover opens comment, no click. Edit mode stays focus-companion. */
export function handleDayDescrCellMouseOver(frm, event) {
	if (isDescriptionPopoverSuppressed(frm)) {
		closeDescriptionPopover();
		return;
	}
	if (canEdit(frm)) {
		return;
	}
	const field = focusColId(event?.column);
	if (!field.startsWith("day_")) {
		return;
	}
	const row = event?.data;
	if (!row || row.rowType !== "position") {
		return;
	}
	if (isSummaryFocus(event, event.node, row, event.eGridCell)) {
		return;
	}
	cancelHoverClose();
	openDescriptionPopover(
		frm,
		row,
		field.slice("day_".length),
		hoverCellEl(event)
	);
}

export function handleDayDescrCellMouseOut(frm, event) {
	if (canEdit(frm)) {
		return;
	}
	const related = event?.event?.relatedTarget;
	if (related && $(related).closest(POPOVER_SEL).length) {
		return;
	}
	scheduleHoverClose();
}

function isMultiCellSelection(table) {
	const ranges = table?.getCellRanges?.() || [];
	if (ranges.length > 1) {
		return true;
	}
	return ranges.some(
		(range) => range.startRowId !== range.endRowId || range.startColId !== range.endColId
	);
}

/** Multi-range, fill drag, or an in-progress pointer gesture (drag not finished). */
function isDescriptionPopoverSuppressed(frm) {
	const table = frm?.ut?.table;
	if (!table) {
		return false;
	}
	if (frm.ut._descrPointerGesture || table._isFillDragging) {
		return true;
	}
	return isMultiCellSelection(table);
}

function focusedDayContext(frm) {
	const api = frm?.ut?.table?.api;
	const focused = api?.getFocusedCell?.();
	if (!api || !focused || focused.rowIndex == null || focused.rowPinned) {
		return null;
	}
	const field = focusColId(focused.column);
	if (!field.startsWith("day_")) {
		return null;
	}
	const node = api.getDisplayedRowAtIndex?.(focused.rowIndex);
	const row = node?.data;
	if (!row || row.rowType !== "position") {
		return null;
	}
	return { row, date: field.slice("day_".length), cellEl: focusedDayCellEl(api) };
}

/** After Ctrl+A / Shift+arrows: close once the range is wider than one cell. */
export function closeDescriptionPopoverIfSuppressed(frm) {
	if (isDescriptionPopoverSuppressed(frm)) {
		closeDescriptionPopover();
	}
}

/** After mouseup: reopen only when the gesture left a single day cell. */
export function syncDescriptionPopoverAfterGesture(frm) {
	if (!frm?.ut) {
		return;
	}
	if (isDescriptionPopoverSuppressed(frm)) {
		closeDescriptionPopover();
		return;
	}
	const ctx = focusedDayContext(frm);
	if (!ctx) {
		return;
	}
	openDescriptionPopover(frm, ctx.row, ctx.date, ctx.cellEl);
}

/**
 * Close the comment popover for the whole pointer gesture.
 * A multi-cell range only exists after the pointer reaches the next cell;
 * by then the popover already covers that cell and the fill-handle hit target.
 */
export function bindDescriptionPopoverGesture(frm, table) {
	const root = table?.container || frm?.ut?.container;
	if (!root || !frm?.ut || frm.ut._descrPopoverGestureBound) {
		return;
	}
	frm.ut._descrPopoverGestureBound = true;

	root.addEventListener(
		"mousedown",
		(event) => {
			const target = event.target;
			if (event.button !== 0) {
				return;
			}
			if (!target?.closest?.(".ag-cell, .dinext-table-fill-handle")) {
				return;
			}
			if (target.closest(".dinext-table-row-reorder-handle")) {
				return;
			}
			frm.ut._descrPointerGesture = true;
			closeDescriptionPopover();
		},
		true
	);

	document.addEventListener("mouseup", () => {
		if (!frm.ut?._descrPointerGesture) {
			return;
		}
		frm.ut._descrPointerGesture = false;
		/* After fill-handle mouseup applies the range. */
		setTimeout(() => syncDescriptionPopoverAfterGesture(frm), 0);
	});
}

/** Alt+↓ / F2 on day cell → focus comment textarea. */
export function handleDayDescrKeyDown(frm, event) {
	const field = event?.colDef?.field || event?.column?.getColId?.() || "";
	if (!field.startsWith("day_")) {
		return;
	}
	if (isSummaryFocus(event, event.node, event.data, event.eGridCell)) {
		return;
	}
	const dom = event.event;
	if (!dom || $(dom.target).closest(POPOVER_SEL).length) {
		return;
	}
	if (!(dom.key === "F2" || (dom.key === "ArrowDown" && dom.altKey))) {
		return;
	}
	if (!$(POPOVER_SEL).length) {
		const row = event.data;
		const date = field.slice("day_".length);
		openDescriptionPopover(frm, row, date, event.eGridCell);
	}
	if (focusDescriptionTextarea()) {
		dom.preventDefault?.();
		dom.stopPropagation?.();
	}
}

/** Close from grid scroll — skip right after open (focus jitter). */
export function closeDescriptionPopoverOnScroll() {
	const openedAt = $(POPOVER_SEL).data("utOpenedAt") || 0;
	if (Date.now() - openedAt < 200) {
		return;
	}
	closeDescriptionPopover();
}

if (typeof frappe !== "undefined" && frappe.router?.on) {
	frappe.router.on("change", closeDescriptionPopover);
}
