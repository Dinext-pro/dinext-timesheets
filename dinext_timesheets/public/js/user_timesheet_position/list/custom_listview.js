/** Port from demodev Client Script Custom_ListView_6.js — ISS-2026-00926 phase 3 */
// Настройки списка User Timesheet Position
frappe.listview_settings["User Timesheet Position"] = {
    hide_name_column: true,
    hide_name_filter: true,
    add_fields: ['custom_username', "document_type", "document_subject", "user_timesheet"],
    onload(listview) {
    },
    formatters: {
        all_hours(val, df, doc) {
            return frappe.format(val, {'fieldtype': 'Data'});
        },
        document_name(val, df, doc) {
            return doc.document_subject ? doc.document_subject: val;
        },
        user(val, df, doc) {
            if (doc) {
                return doc.custom_username;
            }
            return val;
        }
    },
    get_form_link(doc) {
        return frappe.utils.get_form_link(
            "User Timesheet",
            doc.user_timesheet
          );
    },
    refresh: async function(listview) {
        updatetSubjects();
        listview.page.clear_primary_action();
        hideColumnsAndSidebar(listview);
        
        // Инициализируем фильтр при обновлении Тикет -- ISS-2025-01534
        initializePeriodFilter(listview);
    
        try {
            const positions = listview.data.map(doc => ({
                document_name: doc.document_name,
                project_role: doc.project_role
            }));
            
            //const limitsMap = await checkProjectLimitsForAll(positions);
            const utps = listview.data.map(x => x.name);
            
            const userTasks = await frappe.db.get_list('Workflow Task', {
                fields: ['name', 'wt_docname'],
                filters: {
                    doc: "User Timesheet Position",
                    wt_docname: ["in", utps],
                    status: 'Working',
                    "_assign": ["like", "%" + frappe.session.user + "%"] 
                },
                limit: cur_list.page_length
            });
            
            listview.data.forEach(doc => {
                const docname = doc.name;
                const currentStyle = getSelectStyle(doc.status);
                const row = listview.$frappe_list.find(`a[data-name="${docname}"]`)
                    .closest('div.level.list-row');
                
                // Создаем контейнер для кнопок
                const buttonsContainer = $(`
                    <div class="buttons-container" style="display: flex; gap: 5px; margin-left: auto;"></div>
                `);
                
                // Кнопка "План-Факт" Тикет ISS-2025-00472
                const planFactButton = $(`
                    <button class="btn btn-default btn-xs plan-fact-button" 
                            data-docname="${docname}" 
                            title="Показать информацию о плановых и фактических часах"
                            style="width: 24px; height: 24px; padding: 0; border-radius: 50%;">
                        <i class="fa fa-info-circle" style="margin: 0;"></i>
                    </button>
                `);
                
                // Сразу вызываем функцию для обновления стиля кнопки
                //updatePlanFactButtonStyle(planFactButton, doc, limitsMap);
                
                // Кнопка "Details"
                const detailsButton = $(`
                    <button class="btn btn-default btn-xs details-button" 
                            data-docname="${docname}" 
                            title="Нажмите для получения подробностей"
                            style="width: 24px; height: 24px; padding: 0; border-radius: 50%;">
                        <i class="fa fa-list" style="margin: 0;"></i>
                    </button>
                `);
                
                // Кнопка статуса
                const statusButton = $(`
                    <button class="${currentStyle} status-button" 
                            data-docname="${docname}" data-status="${doc.status}">
                        ${doc.status}
                    </button>
                `);
                
                // Добавляем кнопки
                buttonsContainer.append(planFactButton);
                buttonsContainer.append(detailsButton);
                
                addHistoryButton( buttonsContainer, doc );
                
                const holder = row.find('div.level-right.text-muted.ellipsis');
                holder.prepend(buttonsContainer);
                holder.prepend(statusButton);
                
                // Обработчик кнопки "План-Факт"
                planFactButton.on('click', function(e) {
                    e.preventDefault();
                    e.stopPropagation();
                    
                    //console.log('limitsMap при клике:', limitsMap);
                    
                    getHoursData(doc).then(hoursData => {
                        const showForecast = Boolean(frappe.boot && frappe.boot.dinext_timesheet_show_forecast);
                        const forecastValue = Number.isFinite(Number.parseFloat(hoursData.forecastHours))
                            ? Number.parseFloat(hoursData.forecastHours).toFixed(1)
                            : "0.0";
                        let d = new frappe.ui.Dialog({
                            title: "План-Факт анализ",
                            fields: [],
                            size: 'large',
                            primary_action_label: 'Закрыть',
                            primary_action: function() {
                                d.hide();
                            }
                        });
                        
                        // Формируем примечания
                        let hoursNote = '';
                        if (hoursData.usedChildrenForActual && hoursData.hasOwnHours) {
                            hoursNote = `(сумма текущей задачи и ${hoursData.childTasksCount} дочерних)`;
                        } else if (hoursData.usedChildrenForActual) {
                            hoursNote = `(подсчет по ${hoursData.childTasksCount} дочерним задачам)`;
                        } else if (hoursData.hasOwnHours) {
                            hoursNote = `(только текущая задача)`;
                        }
                        
                        // Формируем общее значение плана
                        const planValue = hoursData.plannedHours > 0 ? 
                            `${hoursData.plannedHours.toFixed(1)} ч.` + 
                            (hoursData.usedParentForPlan ? 
                                ` <small>(из <a href="task/${hoursData.parentTaskName}">${hoursData.parentTaskSubject || hoursData.parentTaskName}</a>)</small>` : '') : "-";
                        
                        // Формируем строки таблицы
                        const tableRows = [];
                        
                        // Всего
                        tableRows.push({
                            status: "Всего",
                            plan: planValue,
                            forecast: forecastValue,
                            fact: `${hoursData.totalHours.toFixed(1)} ч. ${hoursNote ? `<small>${hoursNote}</small>` : ''}`,
                            percent: hoursData.plannedHours > 0 ? 
                                Math.round((hoursData.totalHours / hoursData.plannedHours) * 100) : "-"
                        });
                        
                        // Согласовано (если есть часы)
                        if (hoursData.approvedHours > 0) {
                            tableRows.push({
                                status: "Согласовано",
                                plan: planValue,
                                forecast: forecastValue,
                                fact: hoursData.approvedHours.toFixed(1) + " ч.",
                                percent: hoursData.plannedHours > 0 ? 
                                    Math.round((hoursData.approvedHours / hoursData.plannedHours) * 100) : "-"
                            });
                        }
                        
                        // На согласовании (если есть часы)
                        if (hoursData.approvalHours > 0) {
                            tableRows.push({
                                status: "На согласовании",
                                plan: planValue,
                                forecast: forecastValue,
                                fact: hoursData.approvalHours.toFixed(1) + " ч.",
                                percent: hoursData.plannedHours > 0 ? 
                                    Math.round((hoursData.approvalHours / hoursData.plannedHours) * 100) : "-"
                            });
                        }
                        
                        // Редактирование (если есть часы)
                        if (hoursData.editingHours > 0) {
                            tableRows.push({
                                status: "Редактирование",
                                plan: planValue,
                                forecast: forecastValue,
                                fact: hoursData.editingHours.toFixed(1) + " ч.",
                                percent: hoursData.plannedHours > 0 ? 
                                    Math.round((hoursData.editingHours / hoursData.plannedHours) * 100) : "-"
                            });
                        }
                        
                        // Отклонено (если есть часы)
                        if (hoursData.rejectedHours > 0) {
                            tableRows.push({
                                status: "Отклонено",
                                plan: planValue,
                                forecast: forecastValue,
                                fact: hoursData.rejectedHours.toFixed(1) + " ч.",
                                percent: hoursData.plannedHours > 0 ? 
                                    Math.round((hoursData.rejectedHours / hoursData.plannedHours) * 100) : "-"
                            });
                        }
                        
                        const $table = $(`
                            <table class="table table-bordered" style="width: 100%; margin: 15px 0;">
                                <thead>
                                    <tr>
                                        <th>Статус</th>
                                        <th>План</th>
                                        ${showForecast ? `<th>${__("Forecast")}</th>` : ""}
                                        <th>Факт</th>
                                        <th>%</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${tableRows.map(row => `
                                        <tr>
                                            <td>${row.status}</td>
                                            <td>${row.plan}</td>
                                            ${showForecast ? `<td>${row.forecast}</td>` : ""}
                                            <td>${row.fact}</td>
                                            <td>${row.percent !== "-" ? row.percent + "%" : "-"}</td>
                                        </tr>
                                    `).join('')}
                                </tbody>
                            </table>
                        `);
                        
                        d.$wrapper.find('.modal-body').append($table);
                        
                        // 1. Сначала проверяем обязательность плана и его отсутствие
                        if (hoursData.plan_required && hoursData.plannedHours <= 0) {
                            const warningDiv = $(`
                                <div class="alert alert-danger" style="margin: 15px 0;">
                                    <i class="fa fa-exclamation-triangle"></i>
                                    <strong>Внимание!</strong> Для этой задачи обязательно указание плановых трудозатрат!
                                </div>
                            `);
                            d.$wrapper.find('.modal-body').prepend(warningDiv);
                        }
                        // 2. Затем проверяем превышение лимитов (только если план есть)
                        else if (hoursData.plannedHours > 0 && (hoursData.status == "warning" || hoursData.status == "block")) {
                            const warningDiv = $(`
                                <div class="alert alert-${hoursData.status == "warning" ? "warning" : "danger"}" style="margin: 15px 0;">
                                    <i class="fa fa-exclamation-triangle"></i>
                                    <strong>Превышен лимит часов!</strong>
                                    <br>Текущий объем: ${hoursData.totalHours.toFixed(1)} ч. (${hoursData.completionPercentage.toFixed(1)}%)
                                    <br>Лимит: ${(hoursData.plannedHours * hoursData.limit / 100).toFixed(1)} ч. (${hoursData.limit.toFixed(1)}%)
                                </div>
                            `);
                            d.$wrapper.find('.modal-body').prepend(warningDiv);
                        }
                    
                            
                        d.show();
                        setModalWindowStyles(d);
                    });
                });
                
                // Обработчик кнопки "Details"
                detailsButton.on('click', function(e) {
                    e.preventDefault();
                    e.stopPropagation();
                    
                    // Получаем данные из поля table для конкретного документа
                    frappe.db.get_doc('User Timesheet Position', doc.name).then(function(data) {
                        if (data.table && data.table.length > 0) {
                            let d = new frappe.ui.Dialog({
                                title: "Details",
                                fields: [
                                    {
                                        label: __("Задача"),
                                        fieldname: 'first_name',
                                        fieldtype: "Link",
                                        options: data.document_type,
                                        default: data.document_name
                                    },
                                    {
                                        label: 'User Timesheet Position Details',
                                        fieldname: 'table',
                                        fieldtype: 'Table',
                                        cannot_add_rows: 1,
                                        cannot_delete_rows: 1,
                                        in_place_edit: true,
                                        on_setup: null,
                                        fields: [
                                            {
                                                label: 'Date',
                                                fieldname: 'date',
                                                fieldtype: 'Date',
                                                read_only: 1,
                                                in_list_view: 1,
                                                width: 2,
                                                columns: 2
                                            },
                                            {
                                                label: 'Hours',
                                                fieldname: 'hours',
                                                fieldtype: 'Float',
                                                read_only: 1,
                                                in_list_view: 1,
                                                width: 1,
                                                columns: 1
                                            },
                                            {
                                                label: 'Description',
                                                fieldname: 'description',
                                                fieldtype: 'Text',
                                                read_only: 1,
                                                in_list_view: 1,
                                                width: 7,
                                                columns: 7
                                            }
                                        ],
                                        data: data.table
                                    },
                                    {
                                        label: 'Total',
                                        fieldname: 'all_hours',
                                        fieldtype: 'Float',
                                        read_only: 1,
                                        default: data.all_hours || 0
                                    }
                                ],
                                size: 'large',
                                primary_action_label: 'Done',
                                primary_action(details) {
                                    d.hide();
                                    document.activeElement.blur();
                                }
                            });
    
                            d.show();
                            setModalWindowStyles(d);
                        } else {
                            frappe.msgprint(__('Нет данных для отображения.'));
                        }
                    });
                });
                
                // Проверяем доступные переходы статусов
                if (doc.user !== frappe.session.user) {
                    frappe.workflow.get_transitions({ 
                        doctype: "User Timesheet Position", 
                        name: docname 
                    }).then(transitions => {
                        userTask = userTasks.find((task) => task.wt_docname == doc.name);
                        
                        if (userTask && transitions && transitions.length > 0) {
                            const actionHtml = `
                                <select class="${currentStyle} action-dropdown" 
                                        data-docname="${docname}" data-status="${doc.status}">
                                    <option style="font-weight: bold;" value="${doc.status}">${doc.status}</option>
                                    ${transitions.map(transition => 
                                        `<option style="font-weight: bold;" 
                                                value="${transition.next_state}">${transition.action}</option>`
                                    ).join('')}
                                </select>
                            `;
                            statusButton.replaceWith(actionHtml);
                            
                            const dropdown = holder.find(`select.action-dropdown[data-docname="${docname}"]`);
                                
                                // Обработчик изменения статуса (из старого кода)
                                dropdown.on('change', userTask, async function(event) {
                                    const selectedAction = $(this).val();
                                    const selectedTransition = transitions.find(transition => transition.next_state === selectedAction);
            
                                    if (selectedTransition) {
                                        try {
                                            if (selectedTransition.custom_comment_is_required) {
                                                try {
                                                    await showCommentDialog( docname, selectedTransition );
                                                } catch (error) {
                                                    $(this).val(doc.status);
                                                    return;
                                                }
                                            } else {
                                                addToBacklog( docname, selectedTransition.next_state );
                                                processBacklog();
                                            }

                                            frappe.show_alert({
                                                message:__('Данные сохранены'),
                                                indicator:'green'
                                            }, 3);
                                            //updateFilters( listview, docname );
                                        } catch (error) {
                                            console.error('Error updating status:', error);
                                        }
                                    }
                                });
                                
                                // Предотвращаем клик по селекту
                                dropdown.on('click', function(e) {
                                e.stopPropagation();
                            });
                        }
                    });
                }
            });
        } catch (error) {
            console.error("Error in listview refresh:", error);
            frappe.msgprint(__('Произошла ошибка при загрузке данных. Пожалуйста, обновите страницу.'));
        }
        
        //makeResizable();
        processWorkflow(listview);
        refresh_list_limits(listview.data);
    }
};

async function processWorkflow( listview ) {
    if ( frappe.model.has_workflow( listview.doctype ) ) {
        let menu_items = listview.workflow_action_items;
        
        for (action in menu_items) {
            let menu_item = menu_items[action];
            
            $(menu_item).off( "click" );
            $(menu_item).on( "click", {action: action}, async ( event ) => {
                event.stopPropagation();
                let transitions = frappe.workflow.get_all_transitions(listview.doctype);
                let cur_transition = transitions.find((t) => t.action == event.data.action);
                
                if ( cur_transition?.custom_comment_is_required ) {
                    console.log("Need WF action comments..");
                    frappe.prompt({
                        fieldtype: 'Data',
                        label: 'Введите комментарий',
                        fieldname: 'comment',
                        reqd: 1
                    }, async (data) => {
                        if (!data.comment ) {
                            reject("Комментарий не может быть пустым");
                            return;
                        }
                        await updateStatusesMultiple( listview, cur_transition, data.comment );
                    }, `Комментарий для действия "${cur_transition.action}"`, __('Сохранить'));
                    
                } else {
    			    await updateStatusesMultiple( listview, cur_transition );
                }
    		});
    	};
    }
}

async function updateStatusesMultiple( listview, transition, comment ) {
    let items = listview.get_checked_items(true);
    
    if (items.length > 0) {
        addToBacklogMany( items, transition.next_state );
        processBacklog();
        
        if ( comment ) {
            for (item of items) {
                addComment( item, comment );
            }
        }/**/

        frappe.show_alert({
            message:__('Данные сохранены'),
            indicator:'green'
        }, 5);
	}
}

/**function updateFilters( listview, docname ) {
    const taskFilters = listview.filter_area.filter_list.filters[0]?.value;
                                        
    if ( taskFilters ) {
        const taskIndex = taskFilters.indexOf(docname);
        if (taskIndex !== -1) {
            taskFilters.splice(taskIndex, 1);
            listview.filter_area.filter_list.filters[0].set_values(
                "User Timesheet Position", 
                "name", 
                "in", 
                taskFilters
            );
            listview.filter_area.filter_list.filters[0].on_change();
        }
    }
}/**/
/*
function makeResizable() {
    // Изменение ширины столбцов в List View - тикет ISS-2023-00116
    const resultContainer = document.querySelector('.result');
    if (!resultContainer) return;

    const header = resultContainer.querySelector('header');
    const listHeaderSubject = header.querySelector('.list-header-subject');
    const listRowContainers = resultContainer.querySelectorAll('.list-row-container');
    listHeaderSubject.classList.add("ellipsis");
    
    // Получаем сохраненные ширины столбцов
    const storedWidths = JSON.parse(localStorage.getItem(`column_widths_${cur_list.doctype}`) || '{}');

    // Все заголовки столбцов
    const headers = listHeaderSubject.querySelectorAll('.list-row-col');
    headers.forEach((headerDiv, index) => {
        const fieldnameSpan = headerDiv.querySelector('span');
        const fieldname = fieldnameSpan ? fieldnameSpan.textContent.trim() : null;

        // Если это последний столбец (например, assign_to), не меняем ширину
        if (fieldname === 'Assign To' || !fieldname) return;

        // Устанавливаем сохраненную ширину, если она есть
        if (storedWidths[fieldname]) {
            const newWidth = getWidth( storedWidths[fieldname] );
            headerDiv.style.minWidth = newWidth;
            resize( newWidth, index );
        }

        // Создаем элемент для изменения ширины
        const resizer = document.createElement('div');
        resizer.classList.add('column-resizer');
        resizer.setAttribute("data-index", index)
        resizer.addEventListener('mousedown', initResize);

        headerDiv.style.position = 'relative';
        headerDiv.appendChild(resizer);
    });

    function initResize(e) {
        const headerDiv = e.target.parentElement;
        const startX = e.clientX;
        const startWidth = headerDiv.offsetWidth;
        const index = e.target.getAttribute("data-index");
        
        function doResize(event) {
            const newWidth = getWidth( startWidth + (event.clientX - startX) );
            headerDiv.style.minWidth = newWidth;
            resize( newWidth, index );
        }

        function stopResize() {
            document.removeEventListener('mousemove', doResize);
            document.removeEventListener('mouseup', stopResize);

            const fieldnameSpan = headerDiv.querySelector('span');
            const fieldname = fieldnameSpan ? fieldnameSpan.textContent.trim() : null;

            if (fieldname) {
                storedWidths[fieldname] = headerDiv.offsetWidth;
                localStorage.setItem(`column_widths_${cur_list.doctype}`, JSON.stringify(storedWidths));
            }
        }

        document.addEventListener('mousemove', doResize);
        document.addEventListener('mouseup', stopResize);
    }
    
    // Обновляем ширину в строках данных
    function resize(newWidth, index) {
        listRowContainers.forEach(container => {
            const row = container.querySelector('.list-row');
            if (row) {
                const cells = row.querySelectorAll('.list-row-col');
                if (cells[index]) {
                    cells[index].style.minWidth = newWidth;
                }
            }
        });
    }
    
    function getWidth( width ) {
        return "min( 40vw, " + width + "px)";
    }
}/**/

// Остальные вспомогательные функции остаются без изменений
function updatetSubjects() {
    //console.log("updatetSubjects");
    let promises = [];
    
    let tasks = Array.from( new Set(cur_list.data.filter((x) => x.document_type == "Task").map((x) => x.document_name)) );
    let issues = Array.from( new Set(cur_list.data.filter((x) => x.document_type == "Issue").map((x) => x.document_name)) );
    let subjects = cur_list.subjects || [];
    
    let newTasks = tasks.some((x) => !x.document_subject ); 
    let newIssues = issues.some((x) => !x.document_subject ); 

    if (newTasks) {
        promises.push( 
            frappe.db.get_list('Task', {
                fields: ['name', 'subject'],
                filters: [['name', 'IN', tasks ]],
                limit: cur_list.page_length
            }).then(records => {
                //console.log(records);
                subjects.push(records);
                return Promise.resolve();
            }) 
        );
    }
    
    if (newIssues) {
        promises.push( 
            frappe.db.get_list('Issue', {
                fields: ['name', 'subject'],
                filters: [['name', 'IN', issues ]],
                limit: cur_list.page_length
            }).then(records => {
                //console.log(records);
                subjects.push(records);
                return Promise.resolve();
            })
        );
    }
    
    if ( newTasks || newIssues ) {
        Promise.all(promises).then(() => {
            cur_list.subjects = subjects.flat();

            cur_list.subjects.forEach(doc => {
                cur_list.$frappe_list.find(`.list-row-col:contains("${doc.name}")`)
                    .text( doc.subject );
                
                var utp_docs = cur_list.data.filter((element) => element.document_name == doc.name);
                
                if ( utp_docs ) {
                    utp_docs.forEach(utp_doc => {
                        utp_doc.document_subject = doc.subject;
                    });
                }
            });
        }).catch(err => {
            console.error(err);
        });
    }
}

const _backLog = {};
const _filters = [];
const _comments = [];
let _active_request = false;

function addToBacklog( position, status ) {
    addToBacklogMany( [ position ], status );
}

function addToBacklogMany( positions, status ) {
    let bl_positions = _backLog[ status ];
    
    if ( bl_positions && bl_positions.length ) {
        bl_positions.push(...positions);
    } else {
        _backLog[ status ] = positions;
    }
}

function processBacklog() {
    for (const status in _backLog) {
        let positions = _backLog[status];
        console.log(`${status}: ${positions}`);
        
        if ( positions && positions.length ) {
            _backLog[status] = [];
            positions = [...new Set( positions)];
            _filters.push(...positions);
            return updatePositions( positions, status );
        }
    }
    if ( _comments.length ) {
        let comment = _comments.shift();
        
        if ( comment ) {
            return addComment( comment.docname, comment. comment);
        }
    }
    updateList();
}

function updateList() {
    if ( _filters.length ) {
        cur_list.filter_area.filter_list.add_filter( 'User Timesheet Position', 'name', 'not in', _filters, false );
        cur_list.filter_area.debounced_refresh_list_view();
        _filters.length = 0;
    }
}

function updatePositions(updatedPositions, pos_status) {
    if ( _active_request ) {
        addToBacklogMany( updatedPositions, pos_status );
        return;
    }
    
    _active_request = true;
    frappe.call({
        method: "dinext_timesheets.dinext_timesheets.user_timesheet.api.set_timesheet_status",
        args: {
            positions: updatedPositions,
            pos_status: pos_status,
        },
        silent: true,
    }).then(r => {
        _active_request = false;
        processBacklog();
    }).catch(err => { 
        _active_request = false;
        addToBacklogMany( updatedPositions, pos_status );
        catchError( err );
    });
}

function catchError( err ) {
    console.error(err);
    let message;
            
    if ( err && err.responseJSON ) {
        message = err.responseJSON.exception;
    } else {
        message = String( err );
    }
    
    frappe.warn(__("Ошибка при сохранении данных"), message, () => processBacklog(), __("Повторить"), false);
}

async function addComment(docname, comment) {
    if ( _active_request ) {
        _comments.push( { docname: docname, comment: comment } )
        return;
    }
    
    const currentUser = frappe.session.user;
    _active_request = true;
   
    frappe.call({
        method: "frappe.desk.form.utils.add_comment",
        args: {
           reference_doctype: cur_list.doctype,
           reference_name: docname,
           content: comment,
           comment_by: currentUser,
           comment_email: currentUser
       },
       silent: true,
    }).then(r => {
        _active_request = false;
        processBacklog();
    }).catch(err => { 
        _active_request = false;
        _comments.push( { docname: docname, comment: comment } );
        catchError( err ); 
    });
}

//async function showCommentDialog(action, docname, selectedAction) {
async function showCommentDialog( docname, selectedTransition ) {
    return new Promise((resolve, reject) => {
        frappe.prompt({
            fieldtype: 'Data',
            label: 'Введите комментарий',
            fieldname: 'comment',
            reqd: 1
        }, async (data) => {
            if (!data.comment) {
                reject("Комментарий не может быть пустым");
                return;
            }
            
            addToBacklog( docname, selectedTransition.next_state );
            processBacklog();
            addComment(docname, data.comment);
            resolve();
        }, `Комментарий для действия "${selectedTransition.action}"`, __('Сохранить'));
    });
}

function hideColumnsAndSidebar(listview) {
    listview.$result.find('.list-row-head .list-row-col').each(function() {
        const $col = $(this);
        const colname = $col.attr('data-fieldname');
        if (colname && ['name', 'workflow_state'].includes(colname)) {
            $col.hide();
        }
    });
    
    $('.layout-side-section').hide();
    $('.layout-main-section').css('margin-left', '0');
    
    if ( $(document.body).hasClass( "full-width" ) ) {
        frappe.ui.toolbar.toggle_full_width();
    }
}
