frappe.provide("dinext_timesheets.approvals");

dinext_timesheets.approvals.getSelectStyle = function (status) {
	return (
		{
			"Pending Approval": "blue",
			Approved: "green",
			Rejected: "red",
			Editing: "gray",
		}[status] || "gray"
	);
};

dinext_timesheets.approvals.setModalWindowStyles = function (dialog) {
	dialog.$wrapper.find(".modal-dialog").css({
		width: "min(900px, 95vw)",
		"max-width": "95vw",
	});
};

dinext_timesheets.approvals.hideColumnsAndSidebar = function (listview) {
	listview.page.wrapper.find(".layout-side-section").hide();
	listview.page.wrapper.find(".list-liked-by-me").hide();
};

dinext_timesheets.approvals.addHistoryButton = function (parent, position) {
	const button = $(
		`<button class="btn btn-default btn-xs" type="button"
			aria-label="${frappe.utils.escape_html(__("Approval History"))}">
			<span class="fa fa-history" aria-hidden="true"></span>
		</button>`
	);
	$(parent).append(button);
	button.on("click", async (event) => {
		event.preventDefault();
		event.stopPropagation();
		const [workflowRows, legacyComments] = await Promise.all([
			frappe.xcall(
				"dinext_common.workflow_approval.api.get_source_approval_history",
				{
					doctype: "User Timesheet Position",
					name: position.name,
				}
			),
			frappe.db.get_list("Comment", {
				fields: [
					"comment_email",
					"comment_by",
					"comment_type",
					"creation",
					"content",
				],
				filters: {
					reference_doctype: "User Timesheet Position",
					reference_name: position.name,
					comment_type: ["in", ["Workflow", "Comment"]],
				},
				limit: 0,
			}),
		]);
		const rows = [
			...(workflowRows || []).map((row) => ({
				user: row.approver_name,
				date: row.completed_at || row.cancelled_at,
				action: row.action || row.status,
				comment: row.vote_comment || row.cancellation_reason || "",
				source: row.completion_source || "",
			})),
			...(legacyComments || [])
				.filter(
					(row) =>
						row.comment_type === "Comment" ||
						(row.comment_type === "Workflow" &&
							row.content?.startsWith("Выполнена"))
				)
				.map((row) => ({
					user: row.comment_by || row.comment_email,
					date: row.creation,
					action: row.comment_type,
					comment: row.content,
					source: __("Legacy comment"),
				})),
		].sort((left, right) =>
			String(right.date || "").localeCompare(String(left.date || ""))
		);
		const body = rows.length
			? `<div class="table-responsive"><table class="table table-bordered">
				<thead><tr><th>${__("User")}</th><th>${__("Date")}</th>
				<th>${__("Action")}</th><th>${__("Comment")}</th><th>${__(
					"Completion Source"
				)}</th></tr></thead>
				<tbody>${rows
					.map(
						(row) => `<tr>
							<td>${frappe.utils.escape_html(row.user || "")}</td>
							<td>${frappe.datetime.str_to_user(row.date)}</td>
							<td>${frappe.utils.escape_html(row.action || "")}</td>
							<td>${frappe.utils.escape_html(row.comment || "")}</td>
							<td>${frappe.utils.escape_html(row.source || "")}</td>
						</tr>`
					)
					.join("")}</tbody>
			</table></div>`
			: `<p class="text-muted">${__("No records")}</p>`;
		const dialog = new frappe.ui.Dialog({
			title: __("Approval History"),
			size: "large",
		});
		dialog.$body.html(body);
		dinext_timesheets.approvals.setModalWindowStyles(dialog);
		dialog.show();
	});
};
