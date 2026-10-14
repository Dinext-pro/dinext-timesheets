/** Port from demodev Client Script UTP_ListView_Style_2.js — ISS-2026-00926 phase 3 */
// Функция для скрытия столбцов и элементов сайдбара
function hideColumnsAndSidebar(listview) {
    
    //Скрываем сайдбар
    $('span.sidebar-toggle-btn').hide();
    $('.col-lg-2.layout-side-section').hide();
    
    //Скрываем колонку ID
    //listview.$frappe_list.find('.list-row-col.ellipsis.hidden-xs span[data-sort-by="name"]').parent().hide();
    //listview.$frappe_list.find('span[title^="ID"]').closest('.list-row-col.ellipsis.hidden-xs').hide();
    
    //Скрываем колонку Liked by me
    listview.$frappe_list.find('.level-item.list-liked-by-me.hidden-xs span[title="Liked by me"]').parent().hide();
    listview.$frappe_list.find('span[class="like-action not-liked"]').hide();
    
    listview.$frappe_list.find('span[class="modified"]').hide();
}

//Цвет статусов
function getSelectStyle(status) {
    switch (status) {
        case 'Pending Approval':
            return 'on-approve';
        case 'Approved':
            return 'approved';
        case 'Rejected':
            return 'rejected';
        case 'Editing':
            return 'on-edit';
        default:
            return '';
    }
}

// стили модального окна Details (вызов в скрипте User Timesheet Position and Period Filter)
function setModalWindowStyles(modal) {
    
    const cells = modal.$wrapper.find('.static-area')
    for (const cell of cells) {
        cell.classList.remove("ellipsis");
    }

    const cellsCont = modal.$wrapper.find('.grid-static-col');
    for (const cell of cellsCont) {
        cell.style.cssText += 'min-height: 38px; height: auto;';
    }
    
    const checkboxCells = modal.$wrapper.find('.row-check');
    for (const cell of checkboxCells) {
        cell.style.cssText += 'min-height: 38px; height: auto;';
    }

    const style = document.createElement('style');
    style.type = 'text/css';
    style.innerHTML = '.cssClass { display: block !important; }';
    document.getElementsByTagName('head')[0].appendChild(style);

    const staticArea = modal.$wrapper.find('.static-area');
    for (const cell of staticArea) {
        cell.className = 'cssClass';
    }
}


var styles = `
    .list-row-head .level-left,
    .list-row .level-left {
        min-width: 75%;
    }
    .list-row-head .level-right,
    .list-row .level-right {
        overflow-x: hidden !important;
        flex: 2;
    }
    .list-row-activity {
        display: none;
    }
    .status-button, .action-dropdown {
        width: 180px; 
        text-align: center; 
        border-radius: 1em;
        line-height: normal;
    }
    .action-dropdown {
        border: 2px solid;
    }
    .on-approve.action-dropdown {
        border-color: var(--bg-dark-blue);
    }
    .approved.action-dropdown {
        border-color: var(--bg-green);
    }
    .rejected.action-dropdown {
        border-color: var(--bg-red); 
    }
    .on-edit.action-dropdown {
        border-color: var(--bg-grey);
    }
    .status-button {
        border: none; 
        padding-left: 10px;
    }
    .on-approve.status-button {
        background-color: var(--bg-dark-blue);
        color: var(--text-on-blue);
    }
    .approved.status-button {
        background-color: var(--bg-green);
        color: var(--text-on-green);
    }
    .rejected.status-button {
        background-color: var(--bg-red); 
        color: var(--text-on-red);
    }
    .on-edit.status-button {
        background-color: var(--bg-grey);
        color: var(--text-on-grey);
    }
    div.modal-body input[data-fieldname="first_name"] {
        pointer-events: none;   //Неактивное поле Задачи в диалоге
    }
    div.modal-body .row-check {
        display: none;          //Скрыть колонку чек-бокс в диалоге
    }
    div.modal-body .col-xs-4 {
        flex: 0 0 50%;
        max-width: 50%;
    }
    div.modal-body span.comment {
        color: var(--dt-light-red);
    }
    @media (min-width: 768px) {
        .column-resizer {
            cursor: col-resize;
            width: 3px;
            position: absolute;
            right: 0;
            top: 0;
            height: 100%;
            z-index: 10;
            background-color: var(--bg-color);
        }
        .list-row-col {
            min-width: 15px;
        }
    }
`
var styleSheet = document.createElement("style");
styleSheet.textContent = styles;
document.head.appendChild(styleSheet);
