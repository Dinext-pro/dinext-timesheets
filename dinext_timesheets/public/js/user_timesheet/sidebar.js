/**
 * Hide Desk / Dinext workspace rail on User Timesheet form + list.
 * Body class + CSS; toggle must not reopen. Drop class on route leave.
 */

export const UT_SIDEBAR_BODY_CLASS = "ut-hide-desk-sidebar";

function isUserTimesheetRoute() {
	const route = frappe.get_route?.() || [];
	return (
		(route[0] === "Form" || route[0] === "List") &&
		route[1] === "User Timesheet"
	);
}

function bindRouteLeave() {
	if (window._utSidebarRouteBound) {
		return;
	}
	window._utSidebarRouteBound = true;
	$(document).on("page-change.utTimesheetSidebar", () => {
		if (!isUserTimesheetRoute()) {
			removeTimesheetSidebarHide();
		}
	});
}

export function applyTimesheetSidebarHide() {
	document.body.classList.add(UT_SIDEBAR_BODY_CLASS);
	bindRouteLeave();
}

export function removeTimesheetSidebarHide() {
	document.body.classList.remove(UT_SIDEBAR_BODY_CLASS);
	document.body.classList.remove("ut-show-connections");
}
