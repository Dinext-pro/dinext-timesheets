(function () {
frappe.provide("dinext_timesheets.approvals");
if (dinext_timesheets.approvals.timesheetFormInstalled) return;
dinext_timesheets.approvals.timesheetFormInstalled = true;
function applyStyle() {
    // Your CSS as text 
    var styles = `
        #timesheet-table .table-header {
            display: flex; 
            height: 30px;
            background-color: var(--bg-gray);
            color: var(--text-on-gray);
            border-radius: var(--border-radius-sm);
            align-items: center;
            font-weight: bold;
            position: sticky;
            top: 48px;
            z-index: 1;
        }
        #timesheet-table .table-header-cell {
            flex: 1; 
            text-align: center;
        }
        #timesheet-table .column-check {
            max-width: 25px;
			flex-basis: 1%;
			flex-grow: 0;
			flex-shrink: 1;
        }
        #timesheet-table .column-project {
            flex: 2 0 10%;
        }
        #timesheet-table .column-task {
            flex: 3 0 10%;
        }
        #timesheet-table .column-role {
            flex: 1 0 10%;
        }
        
        #timesheet-table .info-button-wrapper {
            flex: 0 0 25px;  /* Фиксированная ширина */
            min-width: 25px; /* Минимальная ширина */
            max-width: 25px; /* Максимальная ширина */
            text-align: center;
            margin-left: 5px;
        }
        
        #timesheet-table .day {
        	flex-basis: 5%;
			flex-grow: 0;
			flex-shrink: 1;
        }
        #timesheet-table .column-total {
        }
        
        #timesheet-table .table-row .dayWrapper.holiday .frappe-control input,
        #timesheet-table .table-apps .AppDayWrapper.holiday .frappe-control input{
            background-color: var(--bg-dark-blue);
        }
        #timesheet-table .table-apps .AppDayWrapper.leave .frappe-control input {
            background-color: var(--bg-green);
        }
        #timesheet-table .table-row {
            display: flex; 
            height: 30px; 
            padding-top: 1px;
            border-top: 1px dotted var(--dark-border-color);
            position: relative;
        }
        #timesheet-table .application_row {
            border-bottom: 1px dotted var(--dark-border-color);
        }
        #timesheet-table .table-row.rejected {
            background-color: var(--error-bg);
        }
        #timesheet-table .table-row.rejected input{
            color: var(--text-on-red);
        }
        #timesheet-table .reject-tooltip {
            display: none;
            position: absolute;
            top: 28px;
            width: 100%;
            background-color: #ff6666;
            color: white;
            padding: 5px 10px;
            border-radius: 3px;
            font-size: 14px;
            font-weight: bold;
            white-space: nowrap;
            z-index: 10;
        }
        #timesheet-table .table-row:hover .reject-tooltip {
            display: block;
        }
        #timesheet-table .dayWrapper {
            flex: 0 0 5%;
        }
        #timesheet-table .apps-header {
            padding: 5px;
        }
        #timesheet-table .table-row .dayWrapper .frappe-control input,
        #timesheet-table .table-apps .AppDayWrapper .frappe-control input { 
            text-align: center;
            border-radius: 0px;
        }
        #timesheet-table .frappe-control input.zero {
            color: var(--secondary);
        }
        #timesheet-table .form-control:disabled, 
        #timesheet-table .form-control[readonly],
        #timesheet-table .table-row .frappe-control input {
            background-color: transparent;
            border-color: var(--border-color);
        }
        #timesheet-table .table-row .frappe-control option {
            background-color: var(--bg-color);
        }
        #timesheet-table .table-total-cell{
            flex: 0 0 5%; 
            text-align: center; 
            max-width:5%;
        }
        #timesheet-table .table-total-input{
            max-width:100%; 
            text-align: center;
        }
        #timesheet-table .AppDayWrapper {
            flex: 0 0 5%;
        }
        #timesheet-table .deleteWrapper {
            flex: 1 0 1%; 
            max-width: 25px; 
            text-align:center;
        }
        #timesheet-table .delete_checkbox {
            vertical-align:-5px; 
            background-color:white;
        }
        #timesheet-table .info-button-wrapper .btn-default {
            background-color: transparent;
        }
    `;
    
    var styleSheet = document.createElement("style");
    styleSheet.textContent = styles;
    document.head.appendChild(styleSheet);
}

applyStyle();

let tasksComplete = {
    'data-loaded': false,
    'rows-created': false
};

//группа глобальных переменных скрипта, т.к. не везде удобно передавать параметр напрямую
let customers;
let apps4Leave;
let filteredHolidays;
let newRowsIndexes = 0;
let customFields = {};

frappe.ui.form.on('User Timesheet', {
	//вызов самой длительной функции загрузки данных, для клиентов, проектов, запросов и задач стартуем сразу же
	//пускаем её в синхроне, чтобы добиться максимальной отзывчивости и скорости отдачи интерфейса пользователю
	onload: async function(frm) {
		//часть изменений интерфейса мы можем так же заготовить в onload
		frm.page.sidebar.remove();
		//cкрываем поле и кнопки заранее, подготавливаем страницу к отрисовке нашего интерфейса
		/**/$('.btn-primary.primary-action').hide();		
		//Скрываем поле timesheet_details на форме
		const anchor = frm.fields_dict["timesheet_details"].wrapper;
		const oldfield = $(anchor).closest('form');
		$(oldfield).hide();
		$(anchor).hide();/**/
		const timesheetName = frm.doc.name;
		const ts_user = frm.doc.timesheet_from;
		const ts_start = frm.doc.ts_valid_from;
		const ts_end = frm.doc.ts_valid_for;
		if(!frm.is_new()){
		    let template_name = await frappe.db.get_value("Worker", { wuser: frm.doc.timesheet_from }, 'wtimesheet_template' );
		    frm.template_doc = await frappe.db.get_doc("Timesheet Template", template_name?.message?.wtimesheet_template );
			
		    frappe.call({
						//method: "dinord_timesheet.utils.loadProjectsRemap2Customers",
						method: "get_timesheet_tasks",
						args: {
								template_name: frm.template_doc.name,
                                ts_start:ts_start,
                                ts_end:ts_end,
                                ts_owner: ts_user
						}
					}).then(function(res){
				        customers = res.message;
				        frm.tasks_data = customers;
				        //console.log(customers);
				        tasksComplete['data-loaded'] = true;
				        //eventEmitter.fire('data-loaded');	  
				        checkIfAllTasksComplete();
					});
		} /**/
	},
	onload_post_render: async function (frm) {
	    disableReprocessJournalEntries(frm);
	    //Тикет -- ISS-2025-01495
	    dinext_timesheets.approvals.disableCopyPosition(frm);
	},
	
	
	//тут решаем две задачи
	validate: async function (frm) {
		//если ТШ создаётся руками, то в нём нет вообще никаких данных
		if(frm.is_new() || frm.doc.__islocal) {
		    //TODO вынести логику в Server Script на событие Before Insert
			//абсолютный минимум - с какого числа создаётся ТШ и чей он
			if(!(frm.doc.ts_valid_from && frm.doc.timesheet_from)){
				frappe.msgprint(__('Please fill in all required fields'));
				frappe.validated = false;
			} else {
				//заполняем оставшиеся поля ТШ исходя из того чей он и с какой даты
				const r_temp = await frappe.db.get_value("Worker", { wuser: frm.doc.timesheet_from }, 'wtimesheet_template' );
				const templ = r_temp.message.wtimesheet_template;
			    
				template_doc = await frappe.db.get_doc("Timesheet Template", templ);
				
				let timesheet_length = 7;
				let reporting_dispatch_period = template_doc.working_days;
				switch(template_doc.ttreporting_period){
					case 'Месячный':
						frm.doc.ts_valid_for = moment( frm.doc.ts_valid_from ).endOf("month").format();
						break;
					case 'Полумесячный':
					    //TODO учитывать кол-во дней в месяце
						timesheet_length = 15;
						frm.doc.ts_valid_for = frappe.datetime.add_days(frm.doc.ts_valid_from, timesheet_length);
						break;
					case 'Недельный':
					    //frm.doc.ts_valid_for = moment( frm.doc.ts_valid_from ).endOf("isoWeek").format();
						//break;
						let eom = moment( frm.doc.ts_valid_from ).endOf("month").format();
					    let eow = moment( frm.doc.ts_valid_from ).endOf("isoWeek").format();
					    frm.doc.ts_valid_for = ( frappe.datetime.get_day_diff( eom, eow ) < 0 ? eom : eow );
						break;
					//case 'Недельный по конец месяца':
					    //let eom = moment( frm.doc.ts_valid_from ).endOf("month").format();
					    //let eow = moment( frm.doc.ts_valid_from ).endOf("isoWeek").format();
					    //frm.doc.ts_valid_for = ( frappe.datetime.get_day_diff( eom, eow ) < 0 ? eom : eow );
						//break;
				}
				
				exists = await testForTS(frm.doc.timesheet_from,frm.doc.ts_valid_from,frm.doc.ts_valid_for);
				if (exists) {
					frappe.msgprint(__('A timesheet already exists that overlaps these dates'));
					frappe.validated = false;				
				}
										
				frm.doc.ts_date_of_dispatch = frappe.datetime.add_days(frm.doc.ts_valid_for, reporting_dispatch_period);
			}	/**/
		
		} else {
			//если ТШ руками не создавался, то просто дёргаем сохранение УТП перед тем как пересохранить ТШ
			//альтернативное решение без сохранения самого ТШ требует сложного обхода встроенной функции сохранения
			//с резервированием его в window, т.к. единожды переназначенный frm.save в refresh сохраняется 
			//до полной перезагрузки страницы
			await saveTimesheet(frm);
			
            // Тикет - ISS-2025-00820
            if (frappe.validated !== false) {
                //Асинхронный вызов, т.к. очень "тяжелая" логика
                dinext_timesheets.approvals.checkLimits(frm)
                .then((warningCheck) => {
                    if (warningCheck.length > 0) {
                        //Убираем дубли
                        warningCheck = warningCheck.uniqBy( JSON.stringify );
                        
                        const message = warningCheck.map(w => 
                            `• <b>${w.task_subject}</b> (Проект: ${w.project}, Роль: ${w.role})<br>` +
                            //`&nbsp;&nbsp;Допустимое превышение: ${w.allowedLimit}%<br>` +
                            `&nbsp;&nbsp;Фактическое трудозатраты: ${w.completion_percentage}% плана`
                        ).join('<br><br>');
                
                        frappe.show_alert({
                            message: `<b>Обратите внимание на следующие задачи:</b><br><br>${message}`,
                            indicator: 'yellow'
                        }, 15);
                    } else {
                        // Сбрасываем все кнопки к стандартному цвету, если нет предупреждений
                        $('#timesheet-table .info-button-wrapper button')
                            .removeClass('btn-warning')
                            .addClass('btn-default');
                    }
                });
            }
        }
    },
	//CSS: вынести, собрать
	refresh: async function (frm) {
	    console.log ('refresh: async function');
	    frm.deletedPositions = [];
		frm.page.sidebar.remove();
		//cкрываем поле заранее, подготавливаем отрисовку, для кейсов после сохранения документа, когда фактически onload заного не триггерится
		$('.btn-primary.primary-action').hide();	
		const anchor = frm.fields_dict["timesheet_details"].wrapper;
		const container = $(anchor).closest('.form-column');
		const oldfield = $(anchor).closest('form');
		$(container).removeClass('col-sm-12');
		$(container).css({'width':'100%'});
		$(oldfield).hide();
		if(frm.is_new() || frm.doc.__islocal) {
			//скрываем лишние поля для новых ТШ
			container.hide()
			//возвращаем кнопку сохранения
			$('.btn-primary.primary-action').show();
		} else {
			//данные ТШ
			const timesheetName = frm.doc.name;
			const ts_user = frm.doc.timesheet_from;
			const ts_start = frm.doc.ts_valid_from;
			const ts_end = frm.doc.ts_valid_for;
			//получаем массив дат ТШ
			const fullDates = getDatesBetween(ts_start, ts_end);
			frm.dates = fullDates;
			
			if ( !fullDates || !fullDates.length ) {
			    frappe.throw(__('Error determining timesheet dates!'))
			}
			
            const workingHoursDoc = ( frm.template_doc?.tt_working_hours_on_date ) 
                ? await frappe.db.get_doc("Working Hours On Date", frm.template_doc.tt_working_hours_on_date )
                : {} ;

            //праздники и выходные
			const lessWorkDays = workingHoursDoc.hod_working_hours_table || []; //неполные рабочие дни
			frm.work_hours = lessWorkDays;
		
			apps4Leave = await loadApplicationsForLeave(frm.doc);
			let holidays = [];
			
			//Очень кривая логика. Мы зачем-то обращаемся к полю fullname, вместо того, чтобы чекать юзера в воркере по полю wuser
			
			if (!frm.is_new()){
				const respHolidayList = await frappe.db.get_value("Worker", { wuser: ts_user }, 'wholiday_list' );
				const holidayList = respHolidayList.message.wholiday_list;
				holidays = await frappe.db.get_doc("Holiday List", holidayList);
				holidays = holidays.holidays;
			} 
			//фильтруем праздники и выходные. Нас интересует только текущая неделя.
			const validFromDate = new Date(ts_start);
			const validForDate = new Date(ts_end);
			let filteredHolidays = holidays.filter(holiday => {
					const holidayDate = new Date(holiday.holiday_date);
					return holidayDate >= validFromDate && holidayDate <= validForDate;
				});
			frm.holidays = filteredHolidays;
			
			const timesheetPositions = await frappe.db.get_list("User Timesheet Position",{
											filters: [
												["user_timesheet", "=", timesheetName]
											],
											fields: ["name","project","project_role","document_type","document_name","status"],//,"reject_reason"],
											limit: 0,
											order_by:'creation asc'
										});
			for (position of timesheetPositions) {
				if(position.status === 'Отклонено') {
				    //const comment = cur_frm.get_docinfo().comments
					const comment = await frappe.db.get_list('Comment', {
						filters: [
							['reference_doctype','=','User Timesheet Position'],
							['reference_name','=',position.name]						
						],
						fields: ['content',"comment_by"],
						limit: 1,
						order_by:'creation desc'
					});/**/
					if(comment?.length>0) {
					    let author = frappe.boot.user_info[ comment[0]?.comment_by ]?.fullname || comment[0]?.comment_by;
					    position.reject_reason = $('<div>' + author + ": " + comment[0]?.content + '</div>').text();
					} else {
					    position.reject_reason = "";
					}
				}
			}

			const parent_names = timesheetPositions.map(record => record.name);
			//данные часов из утп
			let timesheetPositionsWithDetails = await Promise.all(timesheetPositions.map(async (position) => {
															let parentDoc = await frappe.db.get_doc("User Timesheet Position", position.name);
															let childRecords = parentDoc.table || [];
															//отсеиваем все даты из утп, которые не имеют отношения к текущему ТШ
															let filteredChildRecords = childRecords.filter(child =>
																child.date <= frm.doc.ts_valid_for &&
																child.date >= frm.doc.ts_valid_from
															);

															return {
																...position,
																details: filteredChildRecords
															};
															return parentDoc;
														}));
			//Преобразуем в обработчик событий
	        timesheetPositionsWithDetails = frappe.utils.make_event_emitter( timesheetPositionsWithDetails );
	        frm.ts_positions = timesheetPositionsWithDetails;
			//отрисовка
			//проверка на случай если доктайп ТШ поменяют и снесут что-то лишнее
			if (!container) {
				frappe.msgprint(__('Could not find the table container'));
				return;
			}
			
			container.innerHTML = "";
			//если мы открываем другой ТШ, то нужно удалить таблицы перед повторной отрисовкой
			if ($('.table-header').length>0) $('.table-header').remove(); 
			if ($('.table-row').length>0) $('.table-row').remove();
			if ($('.table-total').length>0) $('.table-total').remove(); 			
			//непосредственная отрисовка
			const tableContainer = $('<div id="timesheet-table" style="width: 100%;"></div>').appendTo(container);
			
			createTableHeader( fullDates, filteredHolidays ); //создали заголовок таблицы
			createTableRows(timesheetPositions,frm); //быстро отрисовали УТП
			populateBaseRows( timesheetPositionsWithDetails, fullDates, filteredHolidays );
			drawLeaveApplications( apps4Leave, fullDates, filteredHolidays ); //дорисовали заявки на отсутствие
			
			//разблокируем интерфейся
			enableDataSave(frm, filteredHolidays, fullDates, lessWorkDays);
			//Инициируем массовую загрузку наименований
			loadPositionsTitles( timesheetPositionsWithDetails );
			dinext_timesheets.approvals.refreshLimits(frm);
			
			$(anchor).show();
			container.show();
		}
		showDashboard(frm);
		// Исправления для версии 15.106.0
        await dinext_timesheets.approvals.refreshPendingApprovers(frm);
        //END
		
        // Добавляем в конец функции:
        setTimeout(() => {
            disableReprocessJournalEntries(frm);
            dinext_timesheets.approvals.disableCopyPosition(frm);
            // Другие действия, которые должны выполняться после полного render
        }, 500);
		
	}/**/
});

async function loadPositionsTitles( positions ) {
    const projects = [...new Set( positions.map( position => position.project ) )];
    const tasks = [...new Set( positions.map( position => position.document_name ) )];
    
    loadFormattedValues( positions, projects, "Project", "project_name" );
    loadFormattedValues( positions, tasks, "Task", "subject" );
    loadRoleOptions( positions, projects, cur_frm.doc.timesheet_from, cur_frm.tasks_data );
}

async function loadRoleOptions(positions, projects, user, tasks_data) {
    console.log("Начинаем загрузку опций ролей");
    console.log("Проекты:", projects);
    console.log("Пользователь:", user);

    // Получаем данные о проектах с ролями из серверного метода
    try {
        // Собираем все проекты в плоский массив
        const allProjects = tasks_data.flatMap(customer => 
            Object.values(customer)[0] // Получаем массив проектов для каждого клиента
        );

        // Создаем карту проектов для быстрого доступа
        const projectsMap = {};
        allProjects.forEach(project => {
            projectsMap[project.name] = project;
        });

        // Обрабатываем запрошенные проекты
        projects.forEach(project => {
            console.log(`Обрабатываем проект: ${project}`);
            
            const projectData = projectsMap[project];
            
            if (projectData && projectData.roles) {
                console.log(`Роли для проекта ${project}:`, projectData.roles);
                
                // Создаем событие по загрузке
                positions.trigger("role_options", {
                    project: project,
                    roles: projectData.roles
                });
                console.log(`Событие "role_options" триггерится для проекта ${project}`);
            } else {
                console.log(`Нет данных о ролях для проекта ${project}`);
            }
        });

    } catch (error) {
        console.error("Ошибка при загрузке ролей:", error);
    }
}


async function loadFormattedValues( positions, values, doctype, field ) {
    values.forEach(( value )=>{
		frappe.db.get_value( doctype, value, field, (r) => {
            if (r && r[ field ] ) {
                //Создаем событие по загрузке
                positions.trigger( "formatted_value" , 
                {  
                    doctype: doctype, 
                    value: value,
                    formatted_value: r[ field ]
                } );
            }
        }); 
	});
}

async function showDashboard(frm) {
    frm.dashboard.reset();
    if ( frm.doc.ut_status == "На согласовании") {
        let wfTasks = await frappe.db.get_list('Workflow Task', {
            fields: ['name', '_assign'],
            filters: { 
                status: 'Working',
                state: frm.doc.ut_status,
                doc: "User Timesheet Position",
                wt_docname: ["in", frm.ts_positions?.map((x) => x.name) ],
                "_assign": ["not like", "%" + frm.doc.timesheet_from + "%"] 
            }
        } );
        
        if ( wfTasks && wfTasks.length ) {
            let approvers = Array.from( new Set( wfTasks.map((x) => {
                return  frappe.utils.parse_json( x._assign );
                }).flat() ) );
                
            frappe.db.get_list('User', {
                fields: ['full_name'],
                filters: { 
                    name: ["in", approvers ]
                }
            } ).then( function( users ) {
                approvers = users.map( ( user ) => user.full_name );
                frm.dashboard.add_comment( "Ожидается согласование от: " + frappe.utils.comma_and( approvers ), "blue", permanent = true);
            });
        }
    } 
    if (frm.doc.is_overdue && ( frm.doc.ut_status == 'Черновик' || frm.doc.ut_status == "На доработке") ) {
        frm.dashboard.add_comment(__("Timesheet is overdue! Submit positions for approval immediately!"),"orange",true);
    }
    if ( frm.doc.ut_status == "Согласован") {
        frm.dashboard.add_transactions({
            label: __("Related Documents"),
            items: ["Journal Entry"]
        });
        frm.dashboard.refresh();
    }
}

//проверяем что самые тяжёлые данные загружены и все УТП отрисованы
function checkIfAllTasksComplete() {
    if (tasksComplete['data-loaded'] && tasksComplete['rows-created']) {
        //$('input[data-fieldname^="task"]').attr('readonly', false);
		$('.add-row').show();
		$('.btn-primary.primary-action').show();
    }
}
//получаем массив дат от даты до даты включительно в формате ERPNext
function getDatesBetween(ts_valid_from, ts_valid_for) {
	const dates = [];
	let startDate = ts_valid_from;
	
	while ( frappe.datetime.get_day_diff( startDate, ts_valid_for ) <= 0) {
	    dates.push( startDate );
	    startDate = frappe.datetime.add_days( startDate, 1 );
	}

	return dates;
}

//проверка существования ТШ в интервал 
async function testForTS(user,start,end) {
	const ts_exists_start = await frappe.db.get_list("User Timesheet", {
                                                                        filters: [
                                                                            ["timesheet_from", "=", user],
                                                                            ["ts_valid_from", "<=", start],
                                                                            ["ts_valid_for", ">=", start]
                                                                        ],
                                                                        fields: ["name"],
                                                                        limit: 1
                                                                    });

    const ts_exists_end = await frappe.db.get_list("User Timesheet", {
                                                                        filters: [
                                                                            ["timesheet_from", "=", user],
                                                                            ["ts_valid_from", "<=", end],
                                                                            ["ts_valid_for", ">=", end]
                                                                        ],
                                                                        fields: ["name"],
                                                                        limit: 1
                                                                    });
	return ts_exists_start.length || ts_exists_end.length;
}

//отрисовали заголовок таблицы
 function createTableHeader( fullDates, holidays ) {
	const tableContainer = $('#timesheet-table');
	const headerRow = $('<div class="table-header"></div>').appendTo( tableContainer );
	let daycounter = 1;
	
	createHeaderCell( headerRow, ' ', "column-check" );
	createHeaderCell( headerRow, __("Project"), "column-project" );
	createHeaderCell( headerRow, __("Task"), "column-task" );
	createHeaderCell( headerRow, __("Project Role"), "column-role" );
	
	// Добавляем невидимую колонку такой же ширины, как кнопка
    createHeaderCell(headerRow, ' ', "column-button-spacer");
	
	fullDates.forEach( date => {
	    let holidayClass = ( holidays.some((element) => element.holiday_date == date ) ? " holiday" : "" );
        createHeaderCell( headerRow, moment( date ).format("DD.MM"), "day day_" + daycounter + holidayClass );
        daycounter++;
	});
	
	createHeaderCell( headerRow, __("Total"), "column-total day" );
}

 function createHeaderCell( headerRow, header, cellClass ) {
    let headerCell = $('<div>' + header + '</div>').appendTo( headerRow );
    headerCell.addClass( "table-header-cell" );
    headerCell.addClass( cellClass );
 }

//тянем заявки на отсутствие
async function loadApplicationsForLeave(timesheet) {
	return await frappe.db.get_list('Application For Leave', {
		fields: ['name', 'lauser', 'alfrom_date', 'alto_date','alreasons','altype_of_leave', 'alfrom_hours', 'alto_hours'],
		filters: [
			['lauser', '=', timesheet.timesheet_from],
			['alfrom_date', '<=', timesheet.ts_valid_for],
			['alto_date', '>=', timesheet.ts_valid_from],
			['status','=','Согласовано']
		],
		limit: 1000
	});
}

//создаём в таблице записи UTP
function createTableRows (timesheetPositions,frm) {
	timesheetPositions.forEach((position)=>{
		createBaseRow( position, frm);
	});
	//checkTasksLimitsAndColors( frm );
	tasksComplete['rows-created'] = true;
    //eventEmitter.fire('rows-created');
    checkIfAllTasksComplete();
}

function createDeleteCheckbox(taskRow, name) {
    const deleteWrapper = $('<div class="deleteWrapper">').appendTo(taskRow);
    const deleteCheckbox = $('<input type="checkbox" class="delete_checkbox"></input>')
        .attr( 'name', name )
        .appendTo( deleteWrapper );
    
    deleteCheckbox.on('change', function() {
        if ($('.delete_checkbox:checked').length > 0) {
            $('.delete-timesheet').show();
        } else {
            $('.delete-timesheet').hide();
        }
    });
}

function route( doctype, object ) {
    if ( cur_frm.is_dirty() ) {
        frappe.warn('Вы уверены, что хотите перейти?',
            __('Unsaved timesheet data will be lost!'),
            async () => {
                frappe.set_route('Form', doctype, object);
            },
            __('Continue'),
            true // Sets dialog as minimizable
        );    
    } else {
        frappe.set_route('Form', doctype, object);
    }
}

function createLinkCellL( frm, taskRow, position, controlDF, doctype, field, value, className , select) {
    const wrapper = $('<div></div>').appendTo( taskRow );
    wrapper.addClass( className );
    
    controlDF.change = async function( ){
        let new_value = ( this.df.fieldtype == "Select"
            ? this.get_value()
            : this.$input.attr('data-id') );
        setPositionValue( position.name, field, new_value );
        timesheetDataUpdated();
    }
    
    const control = frappe.ui.form.make_control({
		parent: wrapper[0],
		only_input: true,
		df: controlDF,
		value: value,
        render_input: true
	});
	
	if ( doctype ) {
    	control.$input.off('dblclick').on('dblclick', function (event) {
            event.stopPropagation();
            const object = $(this).data('id');
            if (object) {
                route( doctype, object );
            }
        });/**/
	}
    
    control.$input.attr('readonly', true);
    //control.$input.prop('disabled', 'disabled');
    control.$input.attr('data-id', value );
    control.$input.css('cursor', 'pointer');
    
    frm.ts_positions.on("formatted_value", ( data ) => {
        if ( data ) {
            if ( data.doctype == doctype && data.value == value ) {
                control.set_formatted_input( data.formatted_value );
            }
        }
    });
    
    if ( select ) {
        if ( frm.doc.ut_status == 'Черновик'  || frm.doc.ut_status == 'На доработке' ) {
            control.$input.off("click").on('click', function( event ) {
                event.stopPropagation();
                openTaskSelectionModal( customers, position, $(this), frm );        
            });
        };
    }
    
    customFields[ controlDF.fieldname ] = control;
    return control;
}

function createBaseRowCells( frm, position, taskRow ) {
    createDeleteCheckbox( taskRow, 'delete_' + position.name );
    
    const projectField = createLinkCellL( frm, taskRow, position, 
        {
            fieldtype: 'Data',
			options: '',
			fieldname: 'project_' + position.name,
        }
        , "Project"
        , "project"
        , position.project
        , "column-project"
        , true );
    
    const combinedSelectField = createLinkCellL( frm, taskRow, position,
        {
            fieldtype: 'Data',
			options: '',
			fieldname: 'task_' + position.name,
        }
        , position.document_type
        , "document_name"
        , position.document_name
        , "column-task"
        , true );
        
    let canChange = ( frm.doc.ut_status == 'Черновик' || frm.doc.ut_status == 'На доработке' );
    
    const projectRoleField = createLinkCellL( frm, taskRow, position,
        {
            fieldtype: ( canChange ? 'Select' : 'Data' ),
			options: position.project_role,
			fieldname: 'project_role_' + position.name,
        }
        , ( canChange ? null : 'Project Role' )
        , "project_role"
        , position.project_role
        , "column-role"
        , false );
        
    frm.ts_positions.on("role_options", ( data ) => {
        if ( data && data.roles ) {
            if ( data.project == position.project ) {
                console.log( data );
                projectRoleField.df.options =data.roles;
                projectRoleField.refresh();
            }
        }
    });
    
    // Добавляем кнопку план-факта
    const infoButtonWrapper = $('<div class="info-button-wrapper"></div>').appendTo(taskRow);
    const infoButton = $(`<button id="limits-${position.name}" class="btn btn-default btn-xs"><i class="fa fa-info-circle"></i></button>`)    
        .appendTo(infoButtonWrapper)
        .on('click', function() {
            dinext_timesheets.approvals.showTaskPlanFact(position, frm, $(this));
        });
}


//создаём одну запись из UTP
function createBaseRow(position, frm) {
    const tableContainer = $('#timesheet-table');
    
    const taskRow = $(`<div class="table-row" id="${position.name}"></div>`).appendTo(tableContainer);
    const hiddenType = $(`<input id="tsdoctype_${position.name}" value="${position.document_type}" type="hidden">`).appendTo(taskRow);
    
    if (position.reject_reason?.length > 0 && position.status === 'Отклонено' ) {
        taskRow.addClass("rejected");
        const tooltip = $(`
            <div class="reject-tooltip reject-tooltip-${position.name}">
                ${position.reject_reason}
            </div>
        `);
        tooltip.appendTo(taskRow);
    }
    
    createBaseRowCells( frm, position, taskRow );
    // После создания всех полей добавляем кнопку (Тикет - ISS-2025-00820) по 684
    
    $('#timesheet-table .clearfix').hide();
}

//функция создания новых строк. 
function createNewRow(position,customers,frm,fullDates, holidays) {
    let timesheet = frm.doc;
	$('.table-apps').remove();
	if (position.new){
		position = {
			"new": true,
			"name": newRowsIndexes,
			"user": frm.doc.timesheet_from,
			"project": position.project || "",
			"project_role": position.project_role || "",
			"status": "",
			"period":"",
			"document_type": position.document_type || "Task",
			"document_name": position.document_name || "",
			"all_hours": "",
			"details":[]
		}

		newRowsIndexes++;
		frm.ts_positions.push( position );
	}
	const tableHeader = $('.table-header');
	const tableContainer = $('#timesheet-table');

	const taskRow = $(`<div class="table-row" id="${position.name}"></div>`).appendTo(tableContainer);
	//const newRowFlag = $('<span class="newRow"></span>').appendTo(taskRow);
	const hiddenType = $(`<input id="tsdoctype_${position.name}" value="${position.document_type}" type="hidden" class="newRow">`).appendTo(taskRow);

    createBaseRowCells( frm, position, taskRow );
	populateRow( position, fullDates, holidays );
	
	//т.к. докидываем всегда последней строкой, перерисовываем заявки на отсутствие и пересчитываем\заполняем часы по дню и задаче
	drawLeaveApplications( apps4Leave, fullDates, holidays );
	
	updateTaskTotal(taskRow);
	calculateDayTotal();
	timesheetDataUpdated();
	
	$('#timesheet-table .clearfix').hide();
}

//функция отрисовки модального окна для выбора клиент=>проект=>задача/запрос
function openTaskSelectionModal(customers,position,inputField, frm) {
	if ($('.modal').length) $('.modal').remove();
	if($('.newDescrModal').length){$('.newDescrModal').remove();}
	const modal = $('<div class="modal" style="width: 950px; height: 300px; display: none; display:flex; flex-direction: column;"></div>').appendTo('body');

	const offset = inputField.offset();
	modal.css({
		position: 'absolute',
		top: `${offset.top + inputField.outerHeight()}px`,
		left: `${offset.left}px`
	});

	const modalContent = $('<div class="modal-content" style="display: flex; flex-direction: row; height: 80%; width:100%;"></div>').appendTo(modal);
	const modalButtons = $('<div class="modal-buttons" style="display:flex; flex-direction:row-reverse; height:10%; width:100%;"></div>').appendTo(modal);
	const clientSelect = $('<select id="clientSelect" size=8 style="flex: 0 1 100%; height:100%;"></select>').appendTo(modalContent);
	const projectSelect = $('<select id="projectSelect" size=8 style="flex: 0 1 100%; height:100%; display: none;"></select>').appendTo(modalContent);
	const taskSelect = $('<select id="taskSelect" size=8 style="flex: 0 1 100%; height:100%; min-width:50%; display: none;"></select>').appendTo(modalContent);
	const cancelButton = $('<button style="width:100px;">Отмена</button>').appendTo(modalButtons);
	const selectButton = $('<button style="width:100px;">Выбрать</button>').appendTo(modalButtons);

	let projectList = [];
	let tempRoleSelect = '';
	let projectRoleField = customFields['project_role_' + position.name];

	Object.entries(customers).forEach(([index,client]) => {
		clientSelect.append(new Option(Object.keys(client)[0], index));
	});

	clientSelect.on('change', function() {
		const selectedClient = $(this).val();
		projectSelect.empty().show();
		taskSelect.hide();

		if (selectedClient) {
			projectList = customers[selectedClient][Object.keys(customers[selectedClient])[0]];
			projectList.forEach((project,index) => {
				projectSelect.append(new Option(project.project_name, index));
			});
		}
	});

    let projectField = customFields['project_' + position.name];
    
	projectSelect.on('change', function() {
		const selectedProject = $(this).val();
		taskSelect.empty().show();
		const selectedProjectName = projectSelect.find('option:selected').text();

		if (selectedProject) {
			const projectData = projectList[selectedProject];
			projectField.set_value( projectData.project_name );
			projectField.$input.attr('data-id', projectData.name); 
			
			taskField.$input.attr('data-id', "");
		    taskField.set_value( "" );
			
			if (projectRoleField) {
				projectRoleField.df.options = projectData.roles;
				projectRoleField.refresh();
				
				if (projectData.roles.length === 1) {
				    projectRoleField.set_value( projectData.roles[0] );
				}
			}
			if (projectData) {
				projectData.tasks_issues.forEach(task => {
					let visible_name = task.subject;
					if(task.level) {
					   visible_name = ' '.repeat(task.level)+task.subject;
					}
					let option = new Option(visible_name, task.name);
					option.dataset.tsdoctype = task.tsdoctype;
					taskSelect.append(option);
				});
			}
		}
	});

	let hiddenType = inputField.closest('.table-row').find('input[id^="tsdoctype"]');
	let taskField = customFields['task_' + position.name];
	
	let selectTask = function() {
		const selectedTask = taskSelect.find('option:selected').text();
		taskField.$input.attr('data-id', taskSelect.val());
		taskField.set_value(selectedTask);
		
		hiddenType.val(taskSelect.find('option:selected').data('tsdoctype'));
		modal.remove();
	};

	selectButton.off('click').on('click', selectTask);
	taskSelect.on('dblclick', selectTask);
	
	function clearFields() {
		if(inputField.val().length == 0) {			
			projectField.set_value('');
			projectRoleField.set_value('');
		}		
	}

	cancelButton.off('click').on('click', function() {
		clearFields()
		modal.remove();
	});

	modal.show();
	$(document).off('click.modal').on('click.modal', function(e) {
		//грубо говоря закрываем модалку если ткнули не внутри неё или не на инпут, который её открыл
		if (!$(e.target).closest(modal).length && !$(e.target).is(inputField)) {
			//если не подтвердили выбор кликом по кнопке - чистим поля
			clearFields();
			modal.remove();
		}
	});
	
	frappe.router.on('change', function() {
        if (modal && modal.length) {
            modal.remove();
        }
    });
}

//функция заполнения строк УТП данными по датам (часы/комментарий)
function populateBaseRows( positions, fullDates, holidays ) {
	//прошлись по всем УТП
	positions.forEach((position) => {
	    populateRow( position, fullDates, holidays );
	});
	$('#timesheet-table .clearfix').hide();
}

function populateRow( position, fullDates, holidays ) {
	let taskRow = $('#' + position.name);
	let inputsIndex = 1;
    
	//Для каждой даты в строке утп создали контейнер для часов и комментария
	fullDates.forEach((date, index) => {
	    //проверили, не выходной ли это, если выходной - покрасили ячейку
	    let holidayClass = ( holidays.some((element) => element.holiday_date == date ) ? "holiday" : "" );
		createDateCell( taskRow, position, date, inputsIndex, holidayClass );
		inputsIndex++;
	});

    const totalCell = $('<div class="table-total-cell"><input class="table-total-input" value=0 disabled/></div>').appendTo( taskRow );
    
	//в конце обработки этой записи УТП подсчитали её часы
	updateTaskTotal(taskRow);
}

function createDateCell( taskRow, position, date, inputsIndex, cellClass ) {
    let timesheet = cur_frm.doc;
    const dayWrapper = $('<div class="dayWrapper"></div>').appendTo( taskRow );
    dayWrapper.addClass( cellClass );
		
	let detail = position.details?.find((element) => element.date == date );
    
	$('<input type="hidden" />')
	    .attr('name', `description_${ position.name }_день${ inputsIndex }`)
	    .addClass('description')
	    .val( detail ? detail.description : '')
	    .appendTo( dayWrapper );
	
	if (!dayWrapper[0]) {
		console.error('dayWrapper error');
		return;
	}
	
	const dayInputField = frappe.ui.form.make_control({
		parent: dayWrapper[0],
		only_input: true,
		df: {
			fieldtype: 'Float',
			precision: 2,
			fieldname: `день${inputsIndex}_${date.toLowerCase()}_${position.name}`,
			data: detail ? detail.hours || '0' : '0',
			get input_class() {
			    return ( !this.data || this.data == "0" ) ? "zero" : "";
			},
			get_status: function(i){
                return ( timesheet.ut_status=='Черновик' || timesheet.ut_status=='На доработке') ? "Write" : "Read";
            },
            change: async function(i){
                checkZeroVakue(this.$input, this.value);
				updateTaskTotal(taskRow);
				calculateDayTotal();
				timesheetDataUpdated();
            }
		},
		value: detail ? detail.hours || '0' : '0',
        render_input: true
	});

	customFields[`день${inputsIndex}_${date.toLowerCase()}_${position.name}`] = dayInputField;

    if ( dayInputField.$input ) {
        if ( timesheet.ut_status=='Черновик' || timesheet.ut_status=='На доработке') {
			dayInputField.$input.on('focus', function(event) {
				event.stopPropagation();
				openDescriptionModal(position,$(this),timesheet, dayInputField);
			}); 
        } else {
			dayInputField.$input.on('mouseover', function(event) {
				event.stopPropagation();
				openDescriptionModal(position,$(this),timesheet, dayInputField);
			});
        }
    }
}

function checkZeroVakue( input, value) {
    if ( !value || value == "0" ) {
        input.addClass("zero");
    } else {
        input.removeClass("zero");
    }
}

//функция подсчёта времени по дню недели
function calculateDayTotal() {
	let sumTotals = [];
	if($('.table-row, .table-apps').length > 0) {
		$('.table-row').each(function() {
			let days = $(this).find(".dayWrapper");
			let columnSize = days.length;

            days.each((index, element) => {
				let value = flt($(element).find('input[data-fieldname^="день"]').val()) || 0;
				sumTotals[ index ] = value + ( sumTotals[ index ] || 0 );
                sumTotals[ columnSize ] = value + ( sumTotals[ columnSize ] || 0 );
			});
		});

		if($('.table-apps').length>0){
			$('.application_row').each(function(){
			    let columnSize = $(this).find('.AppDayWrapper').length;
			    
				$(this).find('.AppDayWrapper').each((i,e)=>{
				    let value = parseFloat($(e).find('input').val())
				    sumTotals[ i ] = value + ( sumTotals[ i ] || 0 );
				    sumTotals[ columnSize ] = value + ( sumTotals[ columnSize ] || 0 );
				});
			});
		}

		$('.table-total').remove();

		const totalRow = $('<div class="table-total" style="display:flex; height: 30px; width:100%;"></div>').appendTo('#timesheet-table');
		totalRow.append('<div class="dummy" style="flex: 1 1 10%; min-width:10%;"></div>');
		
		sumTotals.forEach(function(v, i) {
			totalRow.append(`<div class="день${i}_total" style="flex: 0 0 5%; max-width:5%;"><input style="max-width:100%; text-align: center;" value="${v}" disabled/></div>`);					
		});
	}
}
//функция модалки для комментария к количеству часов
function openDescriptionModal(position, inputField, timesheet, inputControl) {
	if($('.newDescrModal').length){$('.newDescrModal').remove();}
	if ($('.modal').length) $('.modal').remove();
	const modal = $('<div class="newDescrModal" style="padding:10px;border-radius:5px;width:300px;height:auto;z-index:999;background:#161a1f;position:absolute;">');

	const offset = inputField.offset();
	modal.css({
		position:'absolute',
		top: `${offset.top + inputField.outerHeight()}px`,
		left: `${offset.left}px`
	});

	const descrInput = inputField.closest('.dayWrapper').find('.description');
	const descrVal = descrInput.val();

	const descriptionInput = $('<textarea class="form-control" rows="5" placeholder="Введите описание"></textarea>')
							   .val(descrVal)
							   .appendTo(modal);
	descriptionInput.on('input', function() {
		descrInput.val($(this).val());
		timesheetDataUpdated();
	});
	
	if((timesheet.ut_status == 'На согласовании' || timesheet.ut_status == 'Согласован' || timesheet.ut_status == 'Отклонено') 
        && !frappe.user.has_role('Dinext_UT_Full_Access')) {
        descriptionInput.attr('disabled',true);
    }
	
	if(timesheet.ut_status != 'На согласовании' && timesheet.ut_status != 'Согласован' && timesheet.ut_status != 'Отклонено') {
		const buttonHolder = $('<div class="tshrs_edit_holder" style="display:flex;justify-content:flex-end;margin-top:10px;">').appendTo(modal);
		$('<button class="btn btn-primary tshrs_incr" style="margin-left:5px;">+30min</button>').appendTo(buttonHolder);
		$('<button class="btn btn-primary tshrs_decr">-30min</button>').appendTo(buttonHolder);
		
		modal.on('click', '.tshrs_incr', function() {
		    inputControl.set_value( inputControl.get_value() + 0.5 );
		});
		
		modal.on('click', '.tshrs_decr', function() {
		    inputControl.set_value( Math.max( inputControl.get_value() - 0.5, 0) );
		});

	}
	$('body').append(modal);

	$(window).off('click.description_modal').on('click.description_modal', function(e) {
		//грубо говоря закрываем модалку если ткнули не внутри неё или не на инпут, который её открыл
		//console.log(e, e.target);
		if (!$(e.target).closest(modal).length && !$(e.target).is(inputField)) {
			modal.remove();
		}
	});
	
	frappe.router.on('change', function() {
        if (modal && modal.length) {
            modal.remove();
        }
    });
}
//подсчёт часов по УТП
function updateTaskTotal(taskRow) {
	let total = 0;
	let inputs = $(taskRow).find("input[data-fieldname^='день']");
	inputs.each(function() {
		const value = flt($(this).val()) || 0;
		total += value;
	});
	$(taskRow).find('.table-total-input').val(total);
	
	let id = taskRow.attr('id');
	if ( id ) {
	    let position = cur_frm.ts_positions.find(( pos ) => pos.name == id );
	    if ( position ) {
	        position.all_hours = total;
	    }
	}
}
//отрисовка заявок на отсутствие
function drawLeaveApplications(leaves, fullDates, holidays) {
	if($('.table-apps').length > 0) {
		$('.table-apps').remove();
	}
	if($('.apps-header').length > 0) {
		$('.apps-header').remove();
	}
	if (leaves.length > 0) {
		const appsHeader = $('<div class="apps-header" style="width:100%;"><b>Заявки на отсутствие:</b></div>').appendTo('#timesheet-table');
		const appsTable = $('<div class="table-apps" style="display:flex; flex-direction:column; width:100%;"></div>').appendTo('#timesheet-table');

		leaves.forEach((leave) => {
			const applicationRow = $('<div class="application_row" style="display:flex; flex-direction:row; height: 30px; width:100%; cursor:pointer;"></div>').appendTo(appsTable);
			const dummyColumn = $('<div class="dummy_column" style="flex: 0 0 2%;"></div>').appendTo(applicationRow);
			const leaveType = $(`<div class="altype" style="flex: 0 0 15%; cursor: pointer;"><input class="input-with-feedback form-control input-xs" style="cursor:pointer;" value="${leave.altype_of_leave}" readonly/></div>`).appendTo(applicationRow);
			const leaveReason = $(`<div class="altype" style="flex: 1 0 43%; cursor:pointer;"><input class="input-with-feedback form-control input-xs" style="cursor:pointer;" value="${leave.name}" readonly/></div>`).appendTo(applicationRow);
			//получаем массив дат
			let appsDates = getDatesBetween(leave.alfrom_date, leave.alto_date);
			//отрисовываем неделю
			fullDates.forEach((date, index) => {
            //for (let i = 1; i < 8; i++) {			    
	            createLeaveDateCell( applicationRow, leave, appsDates, holidays, date, index + 1 );
			});
			
			$('#timesheet-table .clearfix').hide();

			applicationRow.off('dblclick').on('dblclick', function (e) {
				e.stopPropagation();
				route( 'Application For Leave', leave.name )
			});

			const totalCell = $('<div class="table-total-cell" style="flex: 0 0 5%; text-align: center; max-width:5%;"><input class="table-total-input" style="max-width:100%; text-align: center;" value=0 disabled/></div>').appendTo(applicationRow);
			updateTaskTotal(applicationRow);
		});
	}
}

function createLeaveDateCell( applicationRow, leave, appsDates, holidays, date, index ) {
    //проверили, не выходной ли это, если выходной - покрасили ячейку
    const dayWrapper = $('<div class="AppDayWrapper"></div>').appendTo( applicationRow );
	let defaultValue = "0";
    
    if ( holidays.some(day => {return day.holiday_date == date;}) ) {
	    //Если выходной / праздник
	    dayWrapper.addClass("holiday");
	    
    } else if (appsDates.includes( date )) {
		let dayDate = date;
		dayWrapper.addClass("leave");

	    if ( date == leave.alfrom_date ) {
		    //Первый день отсутствия
		    defaultValue = leave.alfrom_hours;
		} else if ( date == leave.alto_date ) {
		    //Последний день отсутствия
		    defaultValue = leave.alto_hours;
		} else {
		    //Рабочий день
		    defaultValue = cur_frm.work_hours.filter(day => {return day.wht_date == date;})[0]?.wht_hours || 
		        cur_frm.template_doc?.hours_on_date;
		}
	}

	const uniqueFieldName = `день${index}_${leave.name.replace(/[^a-zA-Z0-9_]/g, '_')}`;
	
	const dayInputField = frappe.ui.form.make_control({
		parent: dayWrapper[0],
		only_input: true,
		df: {
			fieldtype: 'Data',
			fieldname: uniqueFieldName,
			data: defaultValue,
			get input_class() {
			    return ( !this.data || this.data == "0" ) ? "zero" : "";
			},
			get_status: function(i){
                return "Read";
            }
		},
		value: defaultValue,
        render_input: true
	});

	customFields[uniqueFieldName] = dayInputField;
}


/*
function hideFinProvodkiButton() {
    if (frappe.user.has_role('Dinext_Projects_Director') || 
        frappe.user.has_role('Dinext_Projects_Admin')) {
        return;
    }
        
    // Все возможные варианты селекторов
    const selectors = [
        '.inner-group-button[data-label*="Фин"]', // URL-encoded или обычный текст
        '.btn:contains("Фин. проводки")', // По тексту кнопки
        'button:contains("Фин. проводки")', // Альтернативный вариант
        '[data-label*="проводки"]', // По части атрибута
        'svg[href="#icon-select"]', // По иконке внутри кнопки
    ];

    // Пробуем каждый селектор
    for (const selector of selectors) {
        const element = $(selector).closest('.inner-group-button');
        if (element.length) {
            console.log('Найдено по селектору:', selector, element);
            element.hide().css('display', 'none'); // Двойное скрытие
            return;
        }
    }

    console.error('Кнопка не найдена ни одним селектором');

}
 */

function disableReprocessJournalEntries( frm ) {
    if (frm.doc.ut_status !== 'Согласован' || 
       (!frappe.user.has_role('Dinext_Projects_Director') && 
        !frappe.user.has_role('Dinext_Projects_Admin'))) {  // Добавлена закрывающая скобка
        frm.remove_custom_button("Перепровести", "Фин. проводки");
    }
}

//Тикет -- ISS-2025-01495
//function disableCopyPosition( frm ) {
    //if (frm.doc.ut_status != 'На доработке' && frm.doc.ut_status != 'Черновик') {
        //frm.remove_custom_button("Позиции из предыдущего ТШ", frappe.utils.icon("sidebar-expand") + __("Copy") );
    //}
//}

//логика отрисовки кнопок и включения полей после загрузки данных
async function enableDataSave(frm, filteredHolidays, fullDates, lessWorkDays) {
    //setTimeout(hideFinProvodkiButton, 10);
    calculateDayTotal();
    frm.disable_save();
    
    // Проверяем права
    const isOwner = frappe.session.user == frm.doc.timesheet_from;
    const isSystemManager = frappe.user.has_role('System Manager');
    
    try {
        if (!isOwner && !isSystemManager ) {
            if (!frappe.user.has_role('Dinext_Team_Lead')) {
                return;
            }
            // Получаем текущего тимлида
            const currentTeamLead = await getCurrentTeamLead(
                frm.doc.user_group, 
                frm.doc.ts_valid_from
            );

            if (currentTeamLead != frappe.session.user) {
                return; // Нет прав - выходим
            }
        }

        // Обработка разных статусов. Здесь добавляем || frm.doc.ut_status == 'Согласован' если хотим сохранить согласованный
        if (frm.doc.ut_status == 'Черновик' || frm.doc.ut_status == 'На доработке') {
            frm.remove_custom_button('Остановить воркфлоу');

            // Кнопка удаления
            if ($('.delete-timesheet').length === 0) {
                const buttonContainer = $('<div style="margin-top: 20px;"></div>').appendTo($('#timesheet-table').closest('.section-body'));
                const delButton = $('<button class="btn btn-success delete-timesheet"><i class="fa fa-solid fa-trash"></i></button>');
                
                delButton.appendTo(buttonContainer).hide().on('click', function() {
                    let deletedPositions = frm.deletedPositions || [];
                    $('.delete_checkbox:checked').each(function() {
                        let id = $(this).parent().parent().attr('id');
                        if (!/^\d+$/.test(id)) {
                            deletedPositions.push(id);
                        }
                        $(this).parent().parent().remove();
                    });
                    calculateDayTotal();
                    timesheetDataUpdated();
                    frm.deletedPositions = deletedPositions;
                    $('.delete_checkbox:checked').length == 0 ? delButton.hide() : delButton.show();
                });
            }

            frm.enable_save();
            
            // Кнопка отправки на согласование
            frm.add_custom_button('Отправить на согласование', async function() {
                await sendTimesheet('Start', filteredHolidays, frm, lessWorkDays);
            });

            // Кнопка добавления строки
            if (!$('.add-row').length) {
                $('<button class="btn btn-primary add-row"><i class="fa fa-solid fa-plus"></i></button>')
                    .appendTo($($('.table-header-cell')[0]))
                    .on('click', function() {
                        createNewRow({ "new": true }, customers, frm, fullDates, filteredHolidays);
                    }).hide();
            }
        } 
        else if (frm.doc.ut_status == 'На согласовании') {
            if ($('.add-row').length > 0) {
                $('.add-row').remove();
            }

            frm.remove_custom_button('Отправить на согласование');
            $('.delete-timesheet').hide(); 
            $('.delete_checkbox').hide(); 

            /*
            frm.add_custom_button('Остановить воркфлоу', async function() {
                await sendTimesheet('Stop', filteredHolidays, frm, lessWorkDays);
            });
            
        } 
        */
            // Кнопка "Остановить воркфлоу" только для владельца и System Manager ISS-2025-01001
            //if (isOwner || isSystemManager) {
            //Оставляем только для владельца
            if (isOwner) {
                frm.add_custom_button('Остановить воркфлоу', async function() {
                    await sendTimesheet('Stop', filteredHolidays, frm, lessWorkDays);
                });
            }
        }
        
        else if (['Согласован', 'Отклонено'].includes(frm.doc.ut_status)) {
            if ($('.add-row').length > 0) {
                $('.add-row').remove();
            }
            
            frm.add_custom_button('Вернуть на редактирование', async function() {
                if (frm.doc.ut_status == 'Согласован') { 
                    frappe.warn('Вы уверены, что хотите вернуть ТШ на редактирование?',
                        __('The entire timesheet will require re-approval!'),
                        async () => {
                            await sendTimesheet('Edit', filteredHolidays, frm, lessWorkDays);
                        },
                        __('Continue'),
                        true
                    );
                } else {
                    await sendTimesheet('Edit', filteredHolidays, frm, lessWorkDays);
                }
            });

            frm.remove_custom_button('Отправить на согласование');
            frm.remove_custom_button('Остановить воркфлоу');
        }
        
        checkIfAllTasksComplete();
        
        dinext_timesheets.approvals.addCopyPositionsButton(
            frm,
            customers,
            fullDates,
            filteredHolidays,
            (positions) => {
                positions.forEach((position) => {
                    createNewRow(position, customers, frm, fullDates, filteredHolidays);
                });
                loadPositionsTitles(frm.ts_positions);
                timesheetDataUpdated();
            }
        );
        
        /*
        frm.add_custom_button(__('Positions from Previous Timesheet'), function() {
            disableCopyPosition(frm);
            frappe.call({
                method: 'copy_positions_from_previous_timesheet',
                args: { doc: frm.doc },
                freeze: true,
                silent: true,
                callback: function(r) {
                    // Стандартная обработка ответа
                    handle_copy_positions_response(frm, r);
                    
                    // Отрисовываем строки, если есть данные
                    if (r.message?.success && r.message.data?.positions?.length > 0) {
                        render_copied_positions(
                            frm, 
                            r.message.data.positions, 
                            customers, 
                            fullDates, 
                            filteredHolidays
                        );
                    }
                },
                error: function(err) {
                    handle_copy_positions_error(frm, err);
                }
            });
        }, frappe.utils.icon("sidebar-expand") + __("Copy"));
        */
        
        
    } catch (error) {
        console.error('Ошибка в enableDataSave:', error);
    }
    
}

/*
function enableDataSave(frm, filteredHolidays, fullDates, lessWorkDays) {
	calculateDayTotal();
	frm.disable_save();
//###########################{==ПРОВЕРКИ НА ПОЛЬЗОВАТЕЛЯ И РОЛЬ==}#############################################
    
    //if(frappe.session.user == frm.doc.timesheet_from || frappe.user.has_role('System Manager')) {
    //Расширенная логика для Тимлида. ТИКЕТ -- ISS-2025-01319
    if(frappe.session.user == frm.doc.timesheet_from || frappe.user.has_role('System Manager')|| frappe.user.has_role('Dinext_Team_Lead')) {
    	
//#############################################################################################################    	
    	if (frm.doc.ut_status == 'Черновик' || frm.doc.ut_status == 'На доработке') {
    		frm.remove_custom_button('Остановить воркфлоу');
    
    		if ($('.delete-timesheet').length === 0) {
    			const buttonContainer = $('<div style="margin-top: 20px;"></div>').appendTo($('#timesheet-table').closest('.section-body'));
    
    			const delButton = $('<button class="btn btn-success delete-timesheet"><i class="fa fa-solid fa-trash"></i></button>');
    			delButton.appendTo(buttonContainer).hide().on('click', function() {
    			    let deletedPositions = frm.deletedPositions || [];
    				$('.delete_checkbox:checked').each(async function() {
    					let id = $(this).parent().parent().attr('id');
    					if (!/^\d+$/.test(id)) {
    					    deletedPositions.push(id);
    					}
    					$(this).parent().parent().remove();
    				});
    				calculateDayTotal();
    				timesheetDataUpdated();
    				frm.deletedPositions = deletedPositions;
    				$('.delete_checkbox:checked').length == 0 ? delButton.hide() : delButton.show();
    			});
    		}
    
    		frm.enable_save();
    		//согласование отключено, т.к. не внедрено на проде
    		frm.add_custom_button('Отправить на согласование', async function() {
    			await sendTimesheet('Start', filteredHolidays, frm, lessWorkDays);
    		});
    	
    		if (!$('.add-row').length) {
    			$('<button class="btn btn-primary add-row"><i class="fa fa-solid fa-plus"></i></button>')
    				.appendTo($($('.table-header-cell')[0]))
    				.on('click', function() {
    					createNewRow({ "new": true }, customers, frm, fullDates, filteredHolidays);
    				}).hide();
    		}
    
    	} else if (frm.doc.ut_status == 'На согласовании') {
    		if ($('.add-row').length > 0) {
    			$('.add-row').remove();
    			
    		}
    
    		frm.remove_custom_button('Отправить на согласование');
    		$('.delete-timesheet').hide(); 
            $('.delete_checkbox').hide(); 
    
    		frm.add_custom_button('Остановить воркфлоу', async function() {
    			await sendTimesheet('Stop', filteredHolidays, frm, lessWorkDays);
    		});
    
    	} else {
    		if ($('.add-row').length > 0) {
    			$('.add-row').remove();
    		}
    		
    		//if (frm.doc.ut_status != 'Согласован') { 
        	frm.add_custom_button('Вернуть на редактирование', async function() {
        	    if (frm.doc.ut_status == 'Согласован') { 
            	    frappe.warn('Вы уверены, что хотите вернуть ТШ на редактирование?',
                        __('The entire timesheet will require re-approval!'),
                        async () => {
                            // action to perform if Continue is selected
                            await sendTimesheet('Edit', filteredHolidays, frm, lessWorkDays);
                        },
                        __('Continue'),
                        true // Sets dialog as minimizable
                    )
        	    } else {
        		    await sendTimesheet('Edit', filteredHolidays, frm, lessWorkDays);
        	    }
        	});
    		//}
    
    		frm.remove_custom_button('Отправить на согласование');
    		frm.remove_custom_button('Остановить воркфлоу');
    
    	}
        
    	checkIfAllTasksComplete();
    }
}
*/

// Обновленная функция saveTimesheet (Тикет ISS-2025-00820)
async function saveTimesheet(frm) {
    // 1. Подготовка данных
    const newPositions = [];
    const updatedPositions = [];
    let errors = [];
    const positionsToCheck = [];

    // 2. Сбор данных из формы - только для НЕ удаленных строк
    $('.table-row').each(function(idx) {
        const $row = $(this);
        const position_name = $row.attr('id');
        const isNew = $row.find('.newRow').length > 0;

        const row_task_issue = $row.find('input[data-fieldname^="task"]').data('id');
        const row_project_role = $row.find('select[data-fieldname^="project_role"]').find(":selected").val() || 
                               $row.find('input[data-fieldname^="project_role"]').val();

        if (!row_task_issue) errors.push(`Выберите задачу в строке ${idx + 1}`);
        if (!row_project_role) errors.push(`Выберите роль в строке ${idx + 1}`);

        if (errors.length > 0) return;

        const positionData = {
            doctype: 'User Timesheet Position',
            document_name: row_task_issue,
            document_type: $row.find('input[id^="tsdoctype"]').val(),
            project: $row.find('input[data-fieldname^="project"]').data('id'),
            project_role: row_project_role,
            all_hours: parseFloat($row.find('input.table-total-input').val()) || 0,
            name: position_name
        };

        positionsToCheck.push({...positionData, isNew});

        const fullPosition = {
            ...positionData,
            parent: frm.doc.name,
            user_timesheet: frm.doc.name,
            user: frm.doc.timesheet_from,
            status: ['Черновик', 'На доработке'].includes(frm.doc.ut_status) 
                ? 'Редактирование' 
                : (frm.doc.ut_status == 'Согласован' ? 'Согласовано' : frm.doc.ut_status),
            table: []
        };

        $row.find('.dayWrapper').each(function(dayIdx, day) {
            const date = ($($('.table-header-cell')[dayIdx + 5]).text() + '.' + frm.doc.ts_valid_from.slice(0,4)).split('.').reverse().join('-');
            const hours = flt($(day).find('input[data-fieldname^="день"]').val()) || 0;
            const descr = $(day).find('input[class="description"]').val() || '';
            
            if (hours > 0 || descr.trim().length > 0) {
                fullPosition.table.push({ date, hours, description: descr.trim() });
            }
        });

        if (isNew) {
            newPositions.push(fullPosition);
        } else {
            updatedPositions.push({
                ...fullPosition,
                name: position_name,
                docname: position_name
            });
        }
    });

    // 3. Проверка ошибок
    if (errors.length > 0) {
        frappe.validated = false;
        frappe.msgprint({
            title: __('Unable to save timesheet'),
            indicator: 'red',
            as_list: true,
            message: errors
        });
        return false;
    }

    // 5. Удаление позиций
    const deletedPositions = frm.deletedPositions || [];
    const allToDelete = deletedPositions;
    
    for (const id of allToDelete) {
        try {
            await frappe.call({
                method: 'frappe.client.delete',
                args: {
                    doctype: 'User Timesheet Position',
                    name: id
                },
                freeze: true,
                silent: true
            });
        } catch (error) {
            console.error(`Ошибка удаления позиции ${id}:`, error);
        }
    }
    frm.deletedPositions = [];

    // 6. Сохранение новых позиций
    if (newPositions.length > 0) {
        try {
            await frappe.call({
                method: 'frappe.client.insert_many',
                args: { docs: newPositions },
                freeze: true,
                silent: true,
                freeze_message: __("Saving data..")
            });
        } catch (error) {
            console.error('Ошибка сохранения новых позиций:', error);
            frappe.validated = false;
            frappe.msgprint({
                title: __('Save Error'),
                indicator: 'red',
                message: __('Error saving new positions')
            });
            return false;
        }
    }

    // 7. Обновление существующих позиций
    if (updatedPositions.length > 0) {
        try {
            await frappe.call({
                method: 'frappe.client.bulk_update',
                args: { docs: updatedPositions },
                freeze: true,
                silent: true,
                freeze_message: __("Saving data..")
            });
        } catch (error) {
            console.error('Ошибка обновления позиций:', error);
            frappe.validated = false;
            frappe.msgprint({
                title: __('Save Error'),
                indicator: 'red',
                message: __('Error updating positions')
            });
            return false;
        }
    }

    return true;
}

function timesheet_validation(workflow, filteredHolidays, frm, lessWorkDays) {
    let ts_status = '';
    let pos_status = '';

    if (workflow === 'Start') {
        ts_status = 'На согласовании';
        pos_status = 'На согласовании';
    } else if (workflow === 'Stop' || workflow === 'Edit') {
        ts_status = 'На доработке';
        pos_status = 'Редактирование';
    }

    return new Promise((resolve) => {
        let errors_all = [];
        const newPositions = [];
        const updatedPositions = [];

        const processValidation = () => {
            // Основная логика валидации строк
            //if($('.table-row').first().find('.description').length > filteredHolidays.length) {
                $('.table-row').each(function(idx) {
                    let errors = [];
                    const $row = $(this);
                    const row_project = $row.find('input[data-fieldname^="project"]').first().data('id');
                    const row_tsdoctype = $row.find('input[id^="tsdoctype"]').first().val();
                    const row_task_issue = $row.find('input[data-fieldname^="task"]').data('id');
                    const row_task_issue_readable = $row.find('input[data-fieldname^="task"]').val();
                    const row_project_role = 
                        $row.find('select[data-fieldname^="project_role"]').find(":selected").val() ||
                        $row.find('input[data-fieldname^="project_role"]').val();
                    const position_name = $row.attr('id');
                    const new_position_flag = $row.find('.newRow').length > 0;
                    const total_hours = $row.find('input.table-total-input')[0].value;
                    
                     // ДОБАВЛЕНА ПРОВЕРКА ПРОЕКТА В СВЯЗИ С ИНЦИДЕНТОМ ISS-2025-02619
                    if (!row_project || row_project.length === 0) {
                        errors.push('Выберите проект в ' + (idx + 1) + 'й строке!');
                    }

                    if (!row_task_issue || row_task_issue.length === 0) {
                        errors.push('Выберите запрос или задачу в ' + (idx + 1) + 'й строке!');
                    } 
                    if (!row_project_role || row_project_role.length === 0) {
                        errors.push('Выберите проектную роль в ' + (idx + 1) + 'й строке!');
                    }
                    if ( !total_hours || total_hours == "0" ) {
                        errors.push('Укажите часы в ' + (idx + 1) + 'й строке!');
                    }
                    if (errors.length == 0) {
                        let position = { 
                            doctype: 'User Timesheet Position',
                            parent: frm.doc.name,
                            user_timesheet: frm.doc.name,
                            user: frm.doc.timesheet_from,
                            document_type: row_tsdoctype,
                            document_name: row_task_issue,
                            project: row_project,
                            project_role: row_project_role,
                            status: pos_status,
                            all_hours: total_hours,
                            reject_reason: '',
                            table: []
                        };

                        $row.find('.dayWrapper').each(function(idx, day) {
                            if($(day).find('.description').length != 0) {
                                const date = ($($('.table-header-cell')[idx + 5]).text() + '.' + frm.doc.ts_valid_from.slice(0,4)).split('.').reverse().join('-');
                                const hours = parseFloat($(day).find('input[data-fieldname^="день"]').val()) || 0;
                                const descr = $(day).find('input[class="description"]').val() || '';
                                
                                if (hours > 0 || descr.trim().length > 0) {
                                    position.table.push({ date, hours, description: descr.trim() });
                                }
                                                
                                if (descr.length == 0 && frm.template_doc._is_mandatory && hours > 0) {
                                    errors.push(date + ' по задаче ' + row_task_issue_readable + ' не заполнено описание.');
                                }   
                            }
                        });

                        if (new_position_flag) {
                            newPositions.push(position);
                        } else {
                            updatedPositions.push({
                                doctype: 'User Timesheet Position',
                                name: position_name,
                                ...position
                            });
                        }
                    }
                    errors_all.push(...errors);
                });
            //}

            // Проверка дней
            if ($('.table-total > :not(.dummy)').length > 0) {
                $('.table-total > :not(.dummy)').each(function(idx, day) {
                    const date = ($($('.table-header-cell')[idx + 5]).text() + '.' + frm.doc.ts_valid_from.slice(0,4)).split('.').reverse().join('-');
                    
                    if (frappe.datetime.validate(date)) {
                        const thisDayTotal = parseFloat($(day).find('input').val()) || 0;
                        const hasHolidayDate = filteredHolidays.some(holiday => holiday.holiday_date === date);
                        const hasReducedDay = lessWorkDays.some(day => day.wht_date === date);
                        
                        let day_hours = frm.template_doc.hours_on_date;
                        
                        if(hasReducedDay) {
                            day_hours = lessWorkDays.filter(day => day.wht_date === date)[0].wht_hours;
                        }
                        
                        let minHours = day_hours - frm.template_doc.minimum_hours;
                        let maxHours = day_hours + frm.template_doc.maximum_hours;
                        
                        if (!hasHolidayDate) {
                            if (thisDayTotal < minHours) {
                                errors_all.push(date + ' не может быть менее ' + minHours + ' часов.');
                            }
                            //if (thisDayTotal > maxHours && maxHours > minHours) {
                            if (thisDayTotal > maxHours) {
                                errors_all.push(date + ' не может быть более ' + maxHours + ' часов.');
                            }
                        }
                    }
                });
            } else {
                let start = frm.doc.ts_valid_from;
                while (frappe.datetime.get_diff(frm.doc.ts_valid_for, start) >= 0) {
                    if (!filteredHolidays.some((x) => frappe.datetime.get_diff(start, x.holiday_date) == 0)) {
                        let minHours = lessWorkDays.find(x => frappe.datetime.get_diff(start, x.holiday_date) == 0)?.wht_hours || 
                            frm.template_doc.hours_on_date - frm.template_doc.minimum_hours;
                        
                        if (minHours > 0) {
                            errors_all.push('Добавьте позиции для согласования!');
                            break;
                        }
                    }
                    start = frappe.datetime.add_days(start, 1);
                }
            }

            // Сортировка ошибок
            if (errors_all.length > 0) {
                errors_all = [...new Set(errors_all)];
                errors_all.sort((a, b) => {
                    const dateA = a.substring(0, 5);
                    const [dayA, monthA] = dateA.split('.').map(Number);
                    const fullDateA = new Date(2024, monthA - 1, dayA);
                    const dateB = b.substring(0, 5);
                    const [dayB, monthB] = dateB.split('.').map(Number);
                    const fullDateB = new Date(2024, monthB - 1, dayB);
                    return fullDateA - fullDateB;
                });
            }

            resolve({
                errors_passed: errors_all,
                newPositions: newPositions,
                updatedPositions: updatedPositions
            });
        };
        
        //Вариант с объединенной функцией checkPlannedHoursAndLimits ISS-2025-01298
        if (workflow === 'Start') {
            dinext_timesheets.approvals.checkPlannedHoursAndLimits(frm).then(({errors, warnings, hasCriticalErrors}) => {
                errors_all.push(...errors);
                
                if (hasCriticalErrors) {
                    return resolve({
                        errors_passed: errors_all,
                        newPositions: [],
                        updatedPositions: []
                    });
                }
                
                // Дополнительная обработка warnings если нужно
                processValidation();
            });
        } else {
            processValidation();
        }
        //
    });
}

async function sendTimesheet(workflow, filteredHolidays, frm, lessWorkDays) {
    let ts_status = '';
    let pos_status = '';
    let currentState = "";
    let showErrors = true;

    if (workflow === 'Start') {
        ts_status = 'На согласовании';
        pos_status = 'На согласовании';
        currentState = 'Редактирование';
    } else if (workflow === 'Stop' || workflow === 'Edit') {
        ts_status = 'На доработке';
        pos_status = 'Редактирование';
        currentState = 'На согласовании';
        showErrors = false;
    }

    try {
        const validation_results = await timesheet_validation(workflow, filteredHolidays, frm, lessWorkDays);
        const errors = validation_results.errors_passed || [];
        const newPositions = validation_results.newPositions || [];
        const updatedPositions = validation_results.updatedPositions;
        
        if (showErrors && errors.length > 0) {
            frappe.msgprint({
                title: __('Timesheet filling errors:<br>'),
                indicator: 'red',
                as_list: true,
                message: errors,
                primary_action:{
                    'label': __('Fix'),
                    action(values) {
                        frappe.msg_dialog.cancel();
                    }
                }
            });
            return;
        }
        
        if (newPositions.length + updatedPositions.length != frm.ts_positions.length) {
            frappe.msgprint(__("Error processing timesheet positions. Please refresh the page and try again."));
            return;
        }

        frm.disable_save();

        await dinext_timesheets.approvals.orchestrateTimesheet(
            frm,
            workflow,
            [...newPositions, ...updatedPositions],
            frm.deletedPositions || []
        );
        frm.deletedPositions = [];
        
        frappe.show_alert({
            message: __('Data saved successfully'),
            indicator: 'green'
        }, 5);
        frappe.hide_progress();
        frm.reload_doc();
    } catch (error) {
        frappe.hide_progress();
        console.error("Error updating timesheet:", error);
        if ( frappe.boot.error_report_email && error?.responseJSON?.exc_type != "ValidationError" ) {
            var error_report_message = [
    			"<h4>Отчет об ошибке при обработке ТШ</h4>",
    			"<h5>Укажите дополнительную информацию, которая поможет поддержке воспроизвести проблему:</h5>",
    			'<div style="min-height: 100px; border: 1px solid #bbb; \
    				border-radius: 5px; padding: 15px; margin-bottom: 15px;"></div>',
    			"<hr>",
    			"<h5>ТШ</h5>",
    			"<pre>" + frm.docname + "</pre>",
    			"<hr>",
    			"<h5>Ошибка</h5>",
    			"<pre>" + error + "</pre>",
    		].join("\n");
            var communication_composer = new frappe.views.CommunicationComposer({
    			subject: "Ошибка обработки ТШ [" + frappe.datetime.nowdate() + "]",
    			recipients: frappe.boot.error_report_email,
    			message: error_report_message,
    		});
        } else {
            frappe.msgprint( error?.responseJSON?.exception, __("Error saving timesheet") );
        }
    } finally {
        frm.enable_save();
    }
}

function setPositionValue( name, field, value ) {
    let position = cur_frm.ts_positions.find((pos) => pos.name == name );
    if ( position ) {
        position[ field ] = value;
    }
}

function timesheetDataUpdated() {
    cur_frm?.dirty();
    cur_frm?.remove_custom_button('Отправить на согласование');
    dinext_timesheets.approvals.refreshLimits(cur_frm);
}

// Функция для получения текущего тимлида группы
async function getCurrentTeamLead(user_group, target_date_str) {
    console.log('=== Поиск текущего тимлида ===');
    console.log('Группа:', user_group, '| На дату:', target_date_str);

    try {
        // 1. Получаем документ группы
        const doc = await frappe.db.get_doc('User Group', user_group);
        if (!doc?.custom_table) {
            console.warn('Документ или таблица назначений не найдены');
            return null;
        }

        // 2. Преобразуем дату в формате YYYY-MM-DD
        const target_date = new Date(target_date_str);
        console.log('Все записи назначений:', doc.custom_table);

        // 3. Ищем последнее назначение до целевой даты
        let last_assignment = null;
        
        doc.custom_table.forEach(row => {
            if (!row.date) return;
            
            const assignment_date = new Date(row.date);
            if (assignment_date <= target_date) {
                if (!last_assignment || assignment_date > new Date(last_assignment.date)) {
                    last_assignment = row;
                }
            }
        });

        // 4. Возвращаем результат
        if (last_assignment) {
            console.log('Текущий тимлид:', last_assignment.teamlead, 
                       'назначен', last_assignment.date);
            return last_assignment.teamlead;
        }
        
        console.warn('Нет подходящих назначений');
        return null;

    } catch (e) {
        console.error('Ошибка при поиске тимлида:', e);
        return null;
    }
}

})();
