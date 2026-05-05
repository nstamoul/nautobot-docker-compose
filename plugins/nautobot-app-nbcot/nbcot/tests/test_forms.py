"""Form tests for NBCOT."""

from django.test import TestCase

from nbcot import forms


class CiscoOrderFormTest(TestCase):
    """Test the model and search forms."""

    def test_order_form_accepts_required_fields(self):
        """Order form should validate with the required order number."""
        form = forms.CiscoOrderForm(
            data={
                "order_number": "SO-3001",
                "environment": "poe",
                "status": "Open",
                "is_tracked": True,
            }
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_order_form_requires_order_number(self):
        """Order number is the required field."""
        form = forms.CiscoOrderForm(data={"status": "Open"})
        self.assertFalse(form.is_valid())
        self.assertIn("order_number", form.errors)

    def test_search_form_returns_only_non_empty_filters(self):
        """Search form should strip empty filter inputs."""
        form = forms.OrderSearchForm(
            data={
                "environment": "prod",
                "order_number": "SO-3002",
                "customer_po_number": "",
                "account_name": "Acme",
                "account_number": "",
                "status": "Submitted",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(
            form.cleaned_filters(),
            {"order_number": "SO-3002", "account_name": "Acme", "status": "Submitted"},
        )
        self.assertEqual(form.selected_environment(), "prod")

    def test_ccwr_form_splits_remote_and_local_filters(self):
        """CCW-R form should separate remote search inputs from local line filters."""
        form = forms.CCWRSubscriptionSearchForm(
            data={
                "environment": "prod",
                "subscription_identifier": "205093077",
                "end_customer_name": "AHEPA",
                "from_date": "2022-01-01",
                "to_date": "2035-12-31",
                "pak_serial_number": "6088080510",
                "so_mso_number": "119744472",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_search_filters()["subscription_identifier"], "205093077")
        self.assertEqual(form.cleaned_search_filters()["end_customer_name"], "AHEPA")
        self.assertEqual(form.cleaned_line_filters()["pak_serial_number"], "6088080510")
        self.assertEqual(form.cleaned_line_filters()["so_mso_number"], "119744472")
