/** Port from demodev Client Script User Timesheet Position Function_V3.js — ISS-2026-00926 phase 3 */
async function refresh_list_limits(positions) {
    frappe.call({
        method: 'project_workload_assignment.api.calculate_user_timesheet_limits',
        args: {
            timesheet_name: "",
            positions: positions
        },
        callback: ({ message }) => {
            if ( message) {
                apply_list_limit_styles(message);
            }
        }
    });
}

function apply_list_limit_styles(results) {
    //async function updatePlanFactButtonStyle(button, doc, limitsMap) {
    try {
        // Получаем данные через серверный метод
        //const hoursData = await getHoursData(doc);
        results.forEach(hoursData => {
            const button = $(`button.plan-fact-button[data-docname='${hoursData.position }'`);
            // Устанавливаем стиль кнопки на основе статуса
            setListButtonStyle(button, hoursData.status);
            
            // Формируем подсказку
            let tooltip = hoursData.planned_hours > 0 
                ? `${hoursData.completion_percentage.toFixed( 1 )}% из ${hoursData.planned_hours.toFixed( 1 )} ч.`
                : __("Не определены плановые трудозатраты");
            
            button.attr('title', tooltip);
        });
    } catch (error) {
        console.error('Error updating button style:', error);
        setListButtonStyle(button, 'no-plan');
    }
}

function setListButtonStyle(button, status) {
    const styles = {
        'block': { // Красный - превышена блокировка
            'color': '#f44336'
        },
        'message': { // Оранжевый - превышено уведомление
            'color': '#FF9800'
        },
        'warning': { // Желтый - превышено предупреждение
            'color': '#FFEB3B'
        },
        'normal': { // Зеленый - все в порядке
            'color': '#4CAF50'
        },
        'no-plan': { // Серый - нет плановых данных
            'color': '#9E9E9E'
        }
    };
    
    button.css(styles[status] || styles['no-data']);
}

// Обновленная функция для получения данных план-факт
async function getHoursData(position) {
    try {
        // Используем серверный метод для получения данных
        const result = await frappe.call({
            method: 'project_workload_assignment.api.calculate_user_timesheet_limits',
            args: {
                timesheet_name: '', // Пустое значение, так как мы работаем с отдельными позициями
                positions: [position]
            },
            freeze: false
        });

        if (result && result.message && result.message.length > 0) {
            const data = result.message[0];
            
            return {
                totalHours: data.total_hours || 0,
                editingHours: data.hours_data?.Редактирование || 0,
                approvalHours: data.hours_data?.['На согласовании'] || 0,
                approvedHours: data.hours_data?.Согласовано || 0,
                rejectedHours: data.hours_data?.Отклонено || 0,
                plannedHours: data.planned_hours || 0,
                completionPercentage: data.completion_percentage || 0,
                usedChildrenForActual: data.used_children_for_actual || false,
                usedParentForPlan: data.used_parent_for_plan || false,
                parentTaskName: data.parentTaskName || '',
                parentTaskSubject: data.parentTaskSubject || '',
                taskSubject: data.task_subject || position.document_name,
                childTasksCount: data.child_tasks_count || 0,
                hasOwnHours: data.hasOwnHours || false,
                status: data.status || 'no-plan',
                limit: data.limit,
                // Добавляем недостающие поля:
                plan_required: data.plan_required || false,
                plan_task_subject: data.plan_task_subject || ''
            };
        }
        
        return getDefaultHoursData(position);
    } catch (error) {
        console.error('Error getting hours data:', error);
        return getDefaultHoursData(position);
    }
}

// Функция для получения данных по умолчанию
function getDefaultHoursData(position) {
    return {
        totalHours: 0,
        editingHours: 0,
        approvalHours: 0,
        approvedHours: 0,
        rejectedHours: 0,
        plannedHours: 0,
        completionPercentage: 0,
        usedChildrenForActual: false,
        usedParentForPlan: false,
        parentTaskName: '',
        parentTaskSubject: '',
        taskSubject: position.document_name || '',
        childTasksCount: 0,
        hasOwnHours: false,
        status: 'no-plan',
        // Добавляем недостающие поля:
        plan_required: false,
        plan_task_subject: ''
    };
}
