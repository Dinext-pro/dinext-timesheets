/** Port from demodev Client Script UT_List_Period_Filter_V2.js — ISS-2026-00926 phase 3 */
// тикет ---ISS-2025-01534
let cachedPeriodMap = null;
let cachedToday = null;

function initializePeriodFilter(listview) {  
    if (listview.periodFilterInitialized) return;  
      
    // Создаем контрол через make_control  
    const periodControl = frappe.ui.form.make_control({  
        df: {  
            fieldtype: "Select",  
            label: "",  
            fieldname: "period_filter",  
            options: [  
                "",  
                "Текущая неделя",  
                "Прошлая неделя",   
                "Последние 4 недели",  
                "Текущий месяц",  
                "Прошлый месяц",  
                "Последние 3 месяца",  
                "Текущий квартал",  
                "Прошлый квартал",  
                "Текущий год",  
                "Прошлый год"  
            ].join("\n"),  
            //default: "Текущая неделя",  
            onchange: function() {  
                const periodValue = this.get_value();  
                applyPeriodFilter(periodValue, listview);  
            }  
        },  
        parent: listview.filter_area.standard_filters_wrapper,  
        render_input: true,  
        only_input: false  
    });
      
    // Устанавливаем значение по умолчанию и применяем фильтр  
    //periodControl.set_value("Текущая неделя"); 
    periodControl.$wrapper.find(".clearfix").hide();
      
    listview.periodFilterInitialized = true;  
      
    // Автоматически применяем фильтр по умолчанию  
    //setTimeout(() => {  
        //applyPeriodFilter("Текущая неделя", listview);  
    //}, 100);  
} 

// Функция для инициализации periodMap
function initializePeriodMap(today = null) {
    const currentDate = today || frappe.datetime.now_date();
    
    // Проверяем, нужно ли обновлять кэш
    if (cachedPeriodMap && cachedToday === currentDate) {
        return cachedPeriodMap;
    }
    
    // Инициализируем periodMap
    const periodMap = {  
        "Текущая неделя": [frappe.datetime.week_start(currentDate), frappe.datetime.week_end(currentDate)],  
        "Прошлая неделя": [  
            frappe.datetime.add_days(frappe.datetime.week_start(currentDate), -7),  
            frappe.datetime.add_days(frappe.datetime.week_end(currentDate), -7)  
        ],  
        "Последние 4 недели": [frappe.datetime.add_days(currentDate, -27), currentDate],
        "Текущий месяц": [frappe.datetime.month_start(currentDate), frappe.datetime.month_end(currentDate)],  
        
        "Прошлый месяц": [  
            moment(currentDate).subtract(1, 'month').startOf('month').format('YYYY-MM-DD'),  
            moment(currentDate).subtract(1, 'month').endOf('month').format('YYYY-MM-DD')  
        ],
        "Последние 3 месяца": [frappe.datetime.add_months(frappe.datetime.month_start(currentDate), -2), frappe.datetime.month_end(currentDate)],  
        "Текущий квартал": [frappe.datetime.quarter_start(currentDate), frappe.datetime.quarter_end(currentDate)],  
        "Прошлый квартал": [  
            frappe.datetime.add_months(frappe.datetime.quarter_start(currentDate), -3),  
            frappe.datetime.add_months(frappe.datetime.quarter_end(currentDate), -3)  
        ],  
        "Текущий год": [frappe.datetime.year_start(currentDate), frappe.datetime.year_end(currentDate)],  
        "Прошлый год": [  
            frappe.datetime.add_months(frappe.datetime.year_start(currentDate), -12),  
            frappe.datetime.add_months(frappe.datetime.year_end(currentDate), -12)  
        ]  
    };
    
    // Сохраняем в кэш
    cachedPeriodMap = periodMap;
    cachedToday = currentDate;
    
    return periodMap;
}

function applyPeriodFilter(periodValue, listview) {  
    // Удаляем предыдущий фильтр даты  
    listview.filter_area.remove('date');  
      
    if (!periodValue) return;  
      
    const today = frappe.datetime.now_date();
    
    // Получаем periodMap (с кэшированием)
    const periodMap = initializePeriodMap(today);
      
    const [fromDate, toDate] = periodMap[periodValue];  
    if (fromDate && toDate) {  
        listview.filter_area.add("User Timesheet Position Details", "date", "Between", [fromDate, toDate]);  
    }  
}
