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
            const button = $(`button.plan-fact-button[data-docname='${hoursData.position }']`);
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

// Shared detail presentation; keep the complete server result.
async function showPositionPlanFact(position) {
    const response = await frappe.call({
        method: 'project_workload_assignment.api.calculate_user_timesheet_limits',
        args: { timesheet_name: '', positions: [position] },
        freeze: false
    });
    await frappe.require('/assets/project_workload_assignment/js/limits/plan_fact.js');
    return project_workload_assignment.plan_fact_details.show({
        results: response.message || [],
        title: position.document_subject || position.document_name,
        ownerName: position.custom_username
    });
}
