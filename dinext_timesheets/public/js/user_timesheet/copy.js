/**
 * Copy positions (demodev Copy Previous UT).
 */
import { loadTitles } from "./data.js";
import { refreshRows } from "./toolbar.js";
import { scheduleRefreshLimits } from "./limits.js";

const COPY_PREV =
	"dinext_timesheets.dinext_timesheets.user_timesheet.api.copy_positions_from_previous_timesheet";
const COPY_PWA =
	"dinext_timesheets.dinext_timesheets.user_timesheet.api.copy_positions_from_project_workload_assignment";

function copyGroupLabel() {
	return frappe.utils.icon("sidebar-expand") + __(" Скопировать");
}

/** Same key as server `_position_signature` / demodev Copy Previous UT. */
function getPositionSignature(position) {
	return [
		position?.document_type || "",
		position?.document_name || "",
		position?.user || "",
		position?.project || "",
		position?.project_role || "",
	].join("::");
}

function getExistingPositionSignatures(frm) {
	const signatures = new Set();
	const positions = Array.isArray(frm?.ts_positions) ? frm.ts_positions : [];
	const deletedPositions = Array.isArray(frm?.deletedPositions)
		? frm.deletedPositions
		: [];

	for (const position of positions) {
		if (deletedPositions.includes(position?.name)) {
			continue;
		}
		signatures.add(getPositionSignature(position));
	}
	return signatures;
}

function filterPositionsAlreadyAdded(frm, positions) {
	const existingSignatures = getExistingPositionSignatures(frm);
	const filteredPositions = [];
	let duplicatesCount = 0;

	for (const position of positions) {
		const signature = getPositionSignature(position);
		if (existingSignatures.has(signature)) {
			duplicatesCount++;
			continue;
		}
		existingSignatures.add(signature);
		filteredPositions.push(position);
	}
	return { positions: filteredPositions, duplicatesCount };
}

function handleCopyResponse(result) {
	let message = "";
	let indicator = "orange";
	if (result.copied_count > 0) {
		message = __("Успешно скопировано: {0}", [result.copied_count]);
		indicator = "green";
		if (result.duplicates_count > 0) {
			message += "<br/>";
		}
	}
	if (result.duplicates_count > 0) {
		message += __("Пропущено дубликатов: {0}", [result.duplicates_count]);
	}
	if (!message && result.message) {
		message = result.message;
	}
	frappe.show_alert({ message, indicator }, 8);
}

function extractValidTaskIds(frm) {
	const tasksData = frm.ut?.tasksData || frm.tasks_data;
	if (!tasksData || !Array.isArray(tasksData)) {
		return [];
	}
	const taskIds = [];
	for (const customer of tasksData) {
		for (const customerName in customer) {
			if (!Object.prototype.hasOwnProperty.call(customer, customerName)) {
				continue;
			}
			for (const project of customer[customerName] || []) {
				for (const item of project.tasks_issues || []) {
					if (item.tsdoctype === "Task" && item.name) {
						taskIds.push(item.name);
					}
				}
			}
		}
	}
	return taskIds;
}

async function applyCopiedPositions(frm, positions) {
	const state = frm.ut;
	state._newRowSeq = state._newRowSeq || 0;
	const added = [];
	for (const position of positions) {
		state._newRowSeq += 1;
		const row = {
			...position,
			name: `new_${state._newRowSeq}`,
			new: true,
			user: position.user || frm.doc.timesheet_from,
			details: position.details || [],
			status: "",
		};
		frm.ts_positions.push(row);
		added.push(row);
	}
	await loadTitles(added, frm);
	refreshRows(frm);
	scheduleRefreshLimits(frm);
	frm.dirty();
}

function handleCopyRequest(frm, methodName, validTasks) {
	if (frm._ut_copy_busy) {
		return;
	}
	frm._ut_copy_busy = true;
	frappe.call({
		method: methodName,
		args: {
			doc: frm.doc,
			valid_tasks: validTasks || [],
		},
		freeze: true,
		silent: true,
		callback: async (r) => {
			try {
				const responseMessage =
					r?.message?.message || __("Ошибка при обработке запроса");
				const hasDeletedPositions =
					Array.isArray(frm?.deletedPositions) && frm.deletedPositions.length > 0;

				if (!r?.message?.data) {
					frappe.show_alert(
						{
							message: __("Некорректный формат ответа от сервера"),
							indicator: "red",
						},
						5
					);
					return;
				}
				if (!r.message.success) {
					frappe.show_alert({ message: responseMessage, indicator: "red" }, 5);
					return;
				}
				if (!Array.isArray(r.message.data.positions)) {
					return;
				}

				const filteredResult = filterPositionsAlreadyAdded(
					frm,
					r.message.data.positions
				);
				const responseData = {
					copied_count: filteredResult.positions.length,
					duplicates_count:
						(r.message.data.duplicates_count || 0) +
						filteredResult.duplicatesCount,
					invalid_count: r.message.data.invalid_count || 0,
					message: r.message.message || "",
				};

				if (filteredResult.positions.length === 0) {
					if (
						responseData.invalid_count > 0 ||
						responseData.duplicates_count === 0 ||
						hasDeletedPositions
					) {
						handleCopyResponse(responseData);
					}
					return;
				}

				await applyCopiedPositions(frm, filteredResult.positions);
				handleCopyResponse(responseData);
			} finally {
				frm._ut_copy_busy = false;
			}
		},
		error() {
			frm._ut_copy_busy = false;
			frappe.show_alert(
				{ message: __("Ошибка при обработке запроса"), indicator: "red" },
				5
			);
		},
	});
}

export function disableCopyButtons(frm) {
	const prevLabel = __("Позиции из предыдущего ТШ");
	const pwaLabel = __("Данные из плановой загрузки");
	// Group label has an icon; remove_custom_button(label, group) misses it.
	frm.remove_custom_button(prevLabel);
	frm.remove_custom_button(pwaLabel);
	const $menu = frm.page?.inner_toolbar?.find(".inner-group-button .dropdown-menu");
	if ($menu?.length) {
		$menu.find("li, a").filter((_, el) => {
			const text = (el.textContent || "").trim();
			return text === prevLabel || text === pwaLabel;
		}).remove();
	}
}

/** Form custom buttons in group «Скопировать». */
export function setupCopyButtons(frm) {
	disableCopyButtons(frm);
	if (frm.doc.ut_status !== "Черновик" && frm.doc.ut_status !== "На доработке") {
		return;
	}

	const group = copyGroupLabel();
	frm.add_custom_button(
		__("Позиции из предыдущего ТШ"),
		() => handleCopyRequest(frm, COPY_PREV),
		group
	);
	frm.add_custom_button(
		__("Данные из плановой загрузки"),
		() => handleCopyRequest(frm, COPY_PWA, extractValidTaskIds(frm)),
		group
	);
}
