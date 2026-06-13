"""Test Nautobot_Software_LifecycleExampleModel Filter."""

from nautobot.apps.testing import FilterTestCases

from nautobot_software_lifecycle import filters, models
from nautobot_software_lifecycle.tests import fixtures


class Nautobot_Software_LifecycleExampleModelFilterTestCase(FilterTestCases.FilterTestCase):
    """Nautobot_Software_LifecycleExampleModel Filter Test Case."""

    queryset = models.Nautobot_Software_LifecycleExampleModel.objects.all()
    filterset = filters.Nautobot_Software_LifecycleExampleModelFilterSet
    generic_filter_tests = (
        ("id",),
        ("created",),
        ("last_updated",),
        ("name",),
    )

    @classmethod
    def setUpTestData(cls):
        """Setup test data for Nautobot_Software_LifecycleExampleModel Model."""
        fixtures.create_nautobot_software_lifecycleexamplemodel()

    def test_q_search_name(self):
        """Test using Q search with name of Nautobot_Software_LifecycleExampleModel."""
        params = {"q": "Test One"}
        self.assertEqual(self.filterset(params, self.queryset).qs.count(), 1)

    def test_q_invalid(self):
        """Test using invalid Q search for Nautobot_Software_LifecycleExampleModel."""
        params = {"q": "test-five"}
        self.assertEqual(self.filterset(params, self.queryset).qs.count(), 0)
