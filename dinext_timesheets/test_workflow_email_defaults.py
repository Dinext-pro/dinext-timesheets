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
