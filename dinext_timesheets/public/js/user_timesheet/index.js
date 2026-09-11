import { ensureMounted, destroy } from "./mount.js";
import { saveTimesheetPositions } from "./save.js";
import { canEdit } from "./model.js";
import { setupFormChrome } from "./form_chrome.js";
import { validateNewTimesheet, applyNewTimesheetDefaults } from "./new_doc.js";
import {
	checkLimits,
	checkPlannedHoursAndLimits,
	alertLimitWarnings,
	refreshLimits,
	showTaskPlanFact,
} from "./limits.js";
import { setupSubmitButtons, sendTimesheet } from "./submit.js";
import { applyTimesheetSidebarHide, removeTimesheetSidebarHide } from "./sidebar.js";

let ready = false;

const UserTimesheet = {
	isReady() {
		return ready;
	},
	ensureMounted,
	destroy,
	saveTimesheetPositions,
	validateNewTimesheet,
	applyNewTimesheetDefaults,
	canEdit,
	setupFormChrome,
	setupSubmitButtons,
	sendTimesheet,
	checkLimits,
	checkPlannedHoursAndLimits,
	alertLimitWarnings,
	refreshLimits,
	showTaskPlanFact,
	applyTimesheetSidebarHide,
	removeTimesheetSidebarHide,
};

ready = true;
window.UserTimesheet = UserTimesheet;

export { UserTimesheet };
