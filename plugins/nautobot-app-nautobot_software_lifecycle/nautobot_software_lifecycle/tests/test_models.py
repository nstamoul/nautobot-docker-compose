"""Test Nautobot_Software_LifecycleExampleModel."""

from nautobot.apps.testing import ModelTestCases

from nautobot_software_lifecycle import models
from nautobot_software_lifecycle.tests import fixtures


class TestNautobot_Software_LifecycleExampleModel(ModelTestCases.BaseModelTestCase):
    """Test Nautobot_Software_LifecycleExampleModel."""

    model = models.Nautobot_Software_LifecycleExampleModel

    @classmethod
    def setUpTestData(cls):
        """Create test data for Nautobot_Software_LifecycleExampleModel Model."""
        super().setUpTestData()
        # Create 3 objects for the model test cases.
        fixtures.create_nautobot_software_lifecycleexamplemodel()

    def test_create_nautobot_software_lifecycleexamplemodel_only_required(self):
        """Create with only required fields, and validate null description and __str__."""
        nautobot_software_lifecycleexamplemodel = models.Nautobot_Software_LifecycleExampleModel.objects.create(name="Development")
        self.assertEqual(nautobot_software_lifecycleexamplemodel.name, "Development")
        self.assertEqual(nautobot_software_lifecycleexamplemodel.description, "")
        self.assertEqual(str(nautobot_software_lifecycleexamplemodel), "Development")

    def test_create_nautobot_software_lifecycleexamplemodel_all_fields_success(self):
        """Create Nautobot_Software_LifecycleExampleModel with all fields."""
        nautobot_software_lifecycleexamplemodel = models.Nautobot_Software_LifecycleExampleModel.objects.create(name="Development", description="Development Test")
        self.assertEqual(nautobot_software_lifecycleexamplemodel.name, "Development")
        self.assertEqual(nautobot_software_lifecycleexamplemodel.description, "Development Test")
