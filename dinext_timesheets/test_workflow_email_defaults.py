import unittest
from unittest.mock import MagicMock, patch


class TestWorkflowEmailDefaults(unittest.TestCase):
    def test_legacy_setup_preserves_migrated_email_profile(self):
        from dinext_timesheets.patches.v1_0 import configure_parallel_workflows_v2 as setup
        workflow=MagicMock()
        workflow.get.side_effect=lambda field,default=None: {'custom_email_profile_version':1}.get(field,default)
        workflow.custom_group_workflow_action_emails=1
        workflow.custom_approval_monitor_roles=[]
        with patch.object(setup.frappe,'db',MagicMock(exists=lambda dt,name:dt=='Workflow' and name=='AFL Workflow')), \
             patch.object(setup.frappe,'get_doc',return_value=workflow), \
             patch.object(setup.frappe,'get_all',return_value=[]), \
             patch.object(setup.frappe,'clear_cache'), patch.object(setup,'_ensure_workflow_task_permissions'):
            setup.execute()
        self.assertEqual(workflow.custom_group_workflow_action_emails,1)

    def test_fixture_keeps_current_timesheet_management_routes(self):
        import json
        from pathlib import Path
        workflows=json.loads((Path(__file__).parent/'fixtures/workflow.json').read_text())
        workflow=next(w for w in workflows if w['name']=='UTP Workflow')
        management=[r for r in workflow['transitions']if r['allowed']=='Dinext_Worker']
        self.assertEqual(len(management),4)
        for row in management:
            self.assertEqual(row.get('custom_timesheet_management_action'),1)
            self.assertIn('timesheet_from',row['condition'])
            self.assertIn('date desc, idx desc',row['condition'])
        stop=next(r for r in management if r['state']=='Pending Approval')
        self.assertEqual(stop['action'],'Stop Workflow')
