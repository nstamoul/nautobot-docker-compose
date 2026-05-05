"""Unit tests for views."""

from nautobot.apps.testing import ViewTestCases

from nautobot_software_lifecycle import models
from nautobot_software_lifecycle.tests import fixtures


class Nautobot_Software_LifecycleExampleModelViewTest(ViewTestCases.PrimaryObjectViewTestCase):
    # pylint: disable=too-many-ancestors
    """Test the Nautobot_Software_LifecycleExampleModel views."""

    model = models.Nautobot_Software_LifecycleExampleModel
    bulk_edit_data = {"description": "Bulk edit views"}
    form_data = {
        "name": "Test 1",
        "description": "Initial model",
    }

    update_data = {
        "name": "Test 2",
        "description": "Updated model",
    }

    @classmethod
    def setUpTestData(cls):
        fixtures.create_nautobot_software_lifecycleexamplemodel()
