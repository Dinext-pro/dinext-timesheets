"""Contribution to the shared Workflow cutover from this application."""


def configuration():
    from dinext_timesheets.setup.application_for_leave import SUPERSEDED_SERVER_SCRIPTS

    return {'remove': {'Server Script': ('Workflow Task Assign',
                                  'AFL WT After Save',
                                  'AFL WT Before Save',
                                  'AFL_Deleted_WTs_Deleted',
                                  'UTP Check WT Before Save V2',
                                  'UTP Proccess WT After Save',
                                  'UTP_Deleted_WTs_Deleted',
                                  'Set Timesheet Status',
                                  'UTP_UT_Status_V3',
                                  'Task Limit Exceeded_V4'),
                'Client Script': ('AFL_Approval_V3',
                                  'Множественное_Согласование_AFL_V3',
                                  'WT_To_UTP_Route',
                                  'UT_Accept_WF',
                                  'UTP_History_Data',
                                  'UTP_Route',
                                  'UTP_ListView_Style_2'),
                'Notification': ('Требуется согласование', 'Требуется исправление', 'Согласоанияе ТШ',),
                'Custom DocPerm': ('cdi70531d5', 'g2rmhjbeg2', 'g70iffqseh'),
                'Legacy API': ('set_timesheet_status',)},
     'retain': {'Server Script': (*SUPERSEDED_SERVER_SCRIPTS, 'UTP_comm_2_UT_transfer'), 'Notification': ('Лимит по задаче',)},
     'retained_client_scripts': ('ApFL_Status_Color', 'Custom_ListView_6',
                                 'User_Timesheet_Position_to_User_Timesheet_form_integration_V10'),
     'retained_server_scripts': SUPERSEDED_SERVER_SCRIPTS,
     'canonical_status_consumers': ('project_workload_assignment', 'dinext_project_tasks_gantt'),
     'queue_doctypes': ('Application For Leave', 'User Timesheet', 'User Timesheet Position'),
     'queue_job_modules': ('dinext_timesheets.workflow_approval.',
                           'dinext_timesheets.dinext_timesheets.user_timesheet.events.limits_notify.'),
     'fixture_files': (('dinext_projects', 'fixtures/server_script.json', 'Server Script'),
                       ('dinext_projects', 'fixtures/client_script.json', 'Client Script'),
                       ('dinext_projects', 'fixtures/custom_docperm.json', 'Custom DocPerm'),
                       ('dinext_timesheets', 'fixtures/server_script.json', 'Server Script'),
                       ('dinext_timesheets', 'fixtures/client_script.json', 'Client Script'),
                       ('dinext_timesheets', 'fixtures/custom_docperm.json', 'Custom DocPerm')),
     'notification_files': (('dinext_projects',
                             'dinext_projects/notification/требуется_согласование',
                             'Требуется согласование'),
                            ('dinext_projects',
                             'dinext_projects/notification/требуется_исправление',
                             'Требуется исправление'),
                            ('dinext_timesheets',
                             'dinext_timesheets/notification/согласоанияе_тш',
                             'Согласоанияе ТШ'),),
     "preflight": (20, _preflight),
     "migrate_settings": (10, _migrate_settings),
     "smoke": (10, _smoke)}



def _preflight():
    from dinext_timesheets.patches.v1_0.unify_utp_workflow_status import preflight

    preflight()


def _migrate_settings():
    from dinext_timesheets.patches.v1_0.configure_parallel_workflows_v2 import execute
    from dinext_timesheets.patches.v1_0.unify_utp_workflow_status import migrate
    from dinext_timesheets.workflow_permissions import restore_workflow_task_base_read

    restore_workflow_task_base_read(during_cutover=True)
    migrate()
    execute()


def _smoke():
    import frappe

    from dinext_common.workflow_approval.migration import CutoverBlockedError

    if frappe.db.exists("Workflow", {
        "document_type": "User Timesheet Position",
        "workflow_state_field": ("!=", "status"),
    }):
        raise CutoverBlockedError("Timesheet positions still have a legacy Workflow state field")
