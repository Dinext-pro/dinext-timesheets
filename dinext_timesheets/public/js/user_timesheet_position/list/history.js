/** Port from demodev Client Script UTP_History_Data.js — ISS-2026-00926 phase 3 */
//https://erp.dinord.ru/app/issue/ISS-2025-01932
function addHistoryButton( parent, position ) {
    const historyButton = $(`
        <button class="btn btn-default btn-xs history-button" 
                data-docname="${position.name}" 
                title=${__("История согласования")}
                style="width: 24px; height: 24px; padding: 0; border-radius: 50%; color: var(--text-muted);">
            <i class="fa fa-history" style="margin: 0;" aria-hidden="true"></i>
        </button>
    `);
    parent.append( historyButton );
    
    historyButton.on('click', function(e) {
        e.preventDefault();
        e.stopPropagation();
        
        // Получаем данные для конкретного документа
        frappe.db.get_list('Comment', {
            fields: ['name', 'comment_type', 'creation', 'comment_email', 'content'],
            filters: {
                reference_doctype: 'User Timesheet Position',
                reference_name: position.name,
                comment_type: [ "in", [ "Workflow", "Comment" ] ]
            },
            limit: 0
        }).then(async function(data) {
            if (data && data.length > 0) {
                let emails = Array.from( new Set( data.map( (x) => x.comment_email ) ) );
                
                let users = await frappe.db.get_list('User', {
                    fields: ['name', 'full_name'],
                    filters: { 
                        name: ["in", emails ]
                    }, 
                    limit: emails.length
                } );
                
                for ( var record of data ) {
                    let user = users.find((us) => us.name == record.comment_email);
                    record.full_name = user.full_name;
                }
                
                let d = new frappe.ui.Dialog({
                    title: __("История согласований"),
                    fields: [
                        {
                            label: __("Задача"),
                            fieldname: 'task',
                            fieldtype: "Link",
                            options: position.document_type,
                            default: position.document_name
                        },
                        {
                            label: __("Хронолоогия"),
                            fieldname: 'table',
                            fieldtype: 'Table',
                            cannot_add_rows: 1,
                            cannot_delete_rows: 1,
                            in_place_edit: true,
                            on_setup: null,
                            fields: [
                                {
                                    label: __("Пользователь"),
                                    fieldname: 'full_name',
                                    fieldtype: 'Data',
                                    read_only: 1,
                                    in_list_view: 1,
                                    width: 3,
                                    columns: 3
                                },
                                {
                                    label: __("Дата-время"),
                                    fieldname: 'creation',
                                    fieldtype: 'Date Time',
                                    read_only: 1,
                                    in_list_view: 1,
                                    width: 3,
                                    columns: 3
                                },
                                {
                                    label: __("Запись"),
                                    fieldname: 'content',
                                    fieldtype: 'Text',
                                    read_only: 1,
                                    in_list_view: 1,
                                    width: 4,
                                    columns: 4,
                                    formatter: formatComment
                                }
                            ],
                            data: data.filter(( comm ) => { 
                                return ( comm.comment_type == "Comment" || 
                                    ( comm.comment_type == "Workflow" && comm.content?.startsWith("Выполнена") ) );
                            }),
                        }
                    ],
                    size: 'large',
                    primary_action_label: __('Done'),
                    primary_action(details) {
                        d.hide();
                        document.activeElement.blur();
                    }
                });

                d.show();
            } else {
                frappe.msgprint(__('Нет данных для отображения.'));
            }
        });
    });
    const formatComment = (val, field, options, doc) => {
        return doc.comment_type == "Comment" ? "<span class='comment'>" + val + "</span>" : val;
    }
}
