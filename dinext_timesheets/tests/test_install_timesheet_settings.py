from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from dinext_timesheets import timesheet_settings


class InstallTimesheetSettingsTest(TestCase):
	def test_only_empty_fresh_policy_receives_default_rules(self):
		for position, visible in (([], []), (["configured"], []), ([], ["configured"])):
			with self.subTest(position=position, visible=visible):
				settings = SimpleNamespace(position_rules=position, visible_list_statuses=visible)
				with patch.object(timesheet_settings, "_settings_doc", return_value=settings):
					with patch.object(timesheet_settings, "seed_default_rules") as seed:
						timesheet_settings.seed_installation_rules()
				self.assertEqual(seed.call_count, int(not position and not visible))
