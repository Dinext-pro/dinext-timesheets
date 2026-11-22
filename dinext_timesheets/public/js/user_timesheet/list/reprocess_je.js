/** Port from demodev Client Script UT List Reprocess JE.js — ISS-2026-00926 phase 3 */
function can_reprocess_journal_entries() {
    return !!(
        frappe.user?.has_role?.("Dinext_Projects_Director") ||
        frappe.user?.has_role?.("Dinext_Projects_Admin") ||
        frappe.user?.has_role?.("Z_Dinord_Projects_Director") ||
        frappe.user?.has_role?.("Z_Dinord_Projects_Admin")
    );
}

function add_reprocces_button( listview ) {
    if (can_reprocess_journal_entries()) {
        listview.page.add_action_item(__("Reprocess Journal Entries"), async () => {
            let uts = listview.get_checked_items( false );
            
            const approved_uts = uts.filter(function(element, index) { return element.ut_status == "Approved" });
            
            if ( approved_uts && approved_uts.length ) {
                let total = approved_uts.length ;
                let processed = 0;
                
                frappe.show_progress(__("Posting..."), processed, total);
                
                for (approved_ut of approved_uts) {
                    await reprocces_timesheet( approved_ut );
                    processed++;
                    frappe.show_progress(__("Posting..."), processed, total);
                }
                
                frappe.hide_progress();
                frappe.show_alert({
                    message:__('Data saved'),
                    indicator:'green'
                }, 5);
            }
        });
    }
}

async function reprocces_timesheet( doc ) {
    await frappe.call({  
        method: "process_journal_entries_for_timesheet",
		quiet: true,
		silent: true,
		args: {
			doc: doc,
		},
    });  
}
