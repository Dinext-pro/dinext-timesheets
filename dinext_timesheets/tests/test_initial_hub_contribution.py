from dinext_common.tests.hub_test_utils import HubRegistrationTestCase
from dinext_timesheets.setup.dinext_hub import register_dinext_hub_items


class TestInitialHubContribution(HubRegistrationTestCase):
	def test_timesheets_registers_the_canonical_target_once(self):
		register_dinext_hub_items()
		register_dinext_hub_items()
		self.settings.reload()
		self.assertEqual(len(self.settings.items), 1)
		self.assertEqual(self.settings.items[0].target, "My Timesheets")
		self.assertEqual(self.settings.items[0].source_app, "dinext_timesheets")
