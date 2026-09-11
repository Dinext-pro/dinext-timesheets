/** Port from demodev Client Script UTP_Route.js — ISS-2026-00926 phase 3 */
frappe.ui.form.on('User Timesheet Position', {
    refresh(frm) {
        // Проверяем, есть ли необходимые данные для перенаправления
        if (frm.doc.user_timesheet) {
            //Очистить историю браузера
            history.replaceState(null, null, frappe.router.make_url( frappe.get_prev_route() ) );
            //Перенаправляем пользователя
            frappe.set_route("Form", "User Timesheet", frm.doc.user_timesheet);
            // Устанавливаем таймаут для перенаправления
            //setTimeout(() => {
            //    frappe.set_route('Form', 'User Timesheet', frm.doc.user_timesheet);
            //}, 50); // Увеличиваем задержку до 500 мс
        }
    }
});


/*
frappe.ui.form.on('User Timesheet Position', {
	onload(frm) {
        // Проверяем, есть ли необходимые данные для перенаправления
        if (frm.doc.user_timesheet) {
            // Устанавливаем таймаут для перенаправления,
            // чтобы убедиться, что форма не будет загружена
            setTimeout(() => {
                frappe.set_route('Form', 'User Timesheet', frm.doc.user_timesheet);
            }, 0);
        }
    }
});

*/
