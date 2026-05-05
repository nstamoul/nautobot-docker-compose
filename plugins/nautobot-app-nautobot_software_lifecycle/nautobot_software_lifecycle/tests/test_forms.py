"""Test nautobot_software_lifecycleexamplemodel forms."""

from django.test import TestCase

from nautobot_software_lifecycle import forms


class Nautobot_Software_LifecycleExampleModelTest(TestCase):
    """Test Nautobot_Software_LifecycleExampleModel forms."""

    def test_specifying_all_fields_success(self):
        form = forms.Nautobot_Software_LifecycleExampleModelForm(
            data={
                "name": "Development",
                "description": "Development Testing",
            }
        )
        self.assertTrue(form.is_valid())
        self.assertTrue(form.save())

    def test_specifying_only_required_success(self):
        form = forms.Nautobot_Software_LifecycleExampleModelForm(
            data={
                "name": "Development",
            }
        )
        self.assertTrue(form.is_valid())
        self.assertTrue(form.save())

    def test_validate_name_nautobot_software_lifecycleexamplemodel_is_required(self):
        form = forms.Nautobot_Software_LifecycleExampleModelForm(data={"description": "Development Testing"})
        self.assertFalse(form.is_valid())
        self.assertIn("This field is required.", form.errors["name"])
