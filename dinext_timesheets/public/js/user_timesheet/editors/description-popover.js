import { dayField, descField, sumDayHours, syncPositionFromRow } from "../model.js";
import { buildSummaryRows } from "../summary.js";
import { scheduleRefreshLimits } from "../limits.js";
import { clearInvalidFields } from "../invalid-cells.js";

const POPOVER_NS = ".utDescrPopover";
const POPOVER_SEL = ".ut-descr-popover";
const POPOVER_WIDTH = 252;

function isClosedStatus(frm) {
	return ["На согласовании", "Согласован", "Отклонено"].includes(frm.doc?.ut_status);
}

/**
 * Description edit:
 * - Согласован: always readonly (regulations — no post-approve edits).
 * - На согласовании / Отклонено: Full_Access may edit comment (demodev).
 */
function isDescriptionReadonly(frm) {
	if (frm.doc?.ut_status === "Согласован") {
		return true;
	}
	return isClosedStatus(frm) && !frappe.user.has_role("Dinext_UT_Full_Access");
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

	/* Same cell — reposition / sync, do not remount (keeps cell focus). */
	if (
		$existing.length &&
		$existing.data("utRowId") === String(row.id) &&
		$existing.data("utDate") === date
	) {
		$existing.data({
			utOpenedAt: Date.now(),
			utAnchor: anchorEl,
			utCtx: { frm, row, date },
		});
		$existing.find(".ut-descr-popover__hours").text(hoursLabel(row, date));
		const $ta = $existing.find(".ut-descr-popover__input");
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

	if (descReadonly) {
		$textarea.prop("disabled", true);
	} else {
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

	openDescriptionPopover(frm, row, field.slice("day_".length), cellEl);
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
