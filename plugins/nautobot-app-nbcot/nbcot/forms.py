"""Forms for nbcot."""

from datetime import date

from django import forms
from nautobot.apps.constants import CHARFIELD_MAX_LENGTH
from nautobot.apps.forms import NautobotBulkEditForm, NautobotFilterForm, NautobotModelForm, TagsBulkEditFormMixin

from nbcot import models
from nbcot.choices import CiscoEnvironmentChoices


class CiscoOrderForm(NautobotModelForm):  # pylint: disable=too-many-ancestors
    """CiscoOrder creation/edit form."""

    class Meta:
        """Meta attributes."""

        model = models.CiscoOrder
        fields = (
            "order_number",
            "environment",
            "customer_po_number",
            "account_name",
            "account_number",
            "status",
            "status_detail",
            "lifecycle_state",
            "is_tracked",
            "requested_delivery_date",
            "promised_delivery_date",
            "estimated_delivery_date",
            "ordered_at",
            "last_event_at",
            "tags",
        )


class CiscoOrderBulkEditForm(TagsBulkEditFormMixin, NautobotBulkEditForm):  # pylint: disable=too-many-ancestors
    """CiscoOrder bulk edit form."""

    pk = forms.ModelMultipleChoiceField(queryset=models.CiscoOrder.objects.all(), widget=forms.MultipleHiddenInput)
    is_tracked = forms.NullBooleanField(required=False, label="Tracked")
    environment = forms.ChoiceField(required=False, choices=CiscoEnvironmentChoices, label="Environment")
    status = forms.CharField(required=False, max_length=CHARFIELD_MAX_LENGTH)
    account_name = forms.CharField(required=False, max_length=CHARFIELD_MAX_LENGTH)
    customer_po_number = forms.CharField(required=False, max_length=CHARFIELD_MAX_LENGTH)

    class Meta:
        """Meta attributes."""

        nullable_fields = ["environment", "status", "account_name", "customer_po_number"]


class CiscoOrderFilterForm(NautobotFilterForm):  # pylint: disable=too-many-ancestors
    """Filter form for tracked order list view."""

    model = models.CiscoOrder
    field_order = ["q", "environment", "order_number", "customer_po_number", "account_name", "status", "is_tracked"]

    q = forms.CharField(
        required=False,
        label="Search",
        help_text="Search within order number, PO number, account name, or status.",
    )
    environment = forms.ChoiceField(required=False, choices=CiscoEnvironmentChoices, label="Environment")
    order_number = forms.CharField(required=False, label="Order Number")
    customer_po_number = forms.CharField(required=False, label="Customer PO")
    account_name = forms.CharField(required=False, label="Account")
    status = forms.CharField(required=False, label="Status")
    is_tracked = forms.NullBooleanField(required=False, label="Tracked")


class OrderSearchForm(forms.Form):
    """Ad hoc Cisco search form."""

    environment = forms.ChoiceField(choices=CiscoEnvironmentChoices, label="Environment")
    sales_order_number = forms.CharField(required=False, label="Sales Order No.")
    order_name = forms.CharField(required=False, label="Order Name")
    web_order_id = forms.CharField(required=False, label="Web Order ID")
    subscription_id = forms.CharField(required=False, label="Subscription ID")
    purchase_order = forms.CharField(required=False, label="Purchase Order")
    deal_id = forms.CharField(required=False, label="Deal ID")
    end_customer_name = forms.CharField(required=False, label="End Customer Name")
    end_customer_number = forms.CharField(required=False, label="End Customer No.")
    end_customer_po_number = forms.CharField(required=False, label="End Customer PO No.")
    bill_to_address_id = forms.CharField(required=False, label="Bill to Address ID")
    order_status = forms.CharField(required=False, label="Order Status")

    def cleaned_filters(self):
        """Return non-empty search filters."""
        if not self.is_valid():
            return {}
        return {
            key: value
            for key, value in self.cleaned_data.items()
            if key != "environment" and value not in (None, "")
        }

    def selected_environment(self):
        """Return the selected Cisco API environment."""
        if not self.is_valid():
            return None
        return self.cleaned_data["environment"]


class CCWRSubscriptionSearchForm(forms.Form):
    """CCW-R search and detail lookup form."""

    environment = forms.ChoiceField(choices=CiscoEnvironmentChoices, label="Environment")
    subscription_identifier = forms.CharField(required=False, label="Subscription ID / Contract Number")
    end_customer_name = forms.CharField(required=False, label="End Customer")
    end_customer_site_id = forms.CharField(required=False, label="End Customer Site ID")
    bill_to_id = forms.CharField(required=False, label="Bill To ID")
    status = forms.ChoiceField(
        required=False,
        choices=(
            ("", "---------"),
            ("ACTIVE", "ACTIVE"),
            ("SIGNED", "SIGNED"),
            ("EXPIRED", "EXPIRED"),
            ("TERMINATED", "TERMINATED"),
            ("CANCELLED", "CANCELLED"),
        ),
        label="Status",
    )
    from_date = forms.DateField(required=False, label="From Date", initial=date(2022, 1, 1))
    to_date = forms.DateField(required=False, label="To Date", initial=date(2035, 12, 31))
    pak_serial_number = forms.CharField(required=False, label="PAK / Serial / Instance")
    so_mso_number = forms.CharField(required=False, label="SO / MSO Number")
    po_mpo_number = forms.CharField(required=False, label="PO / MPO Number")
    line_end_customer = forms.CharField(required=False, label="Line End Customer")

    def cleaned_search_filters(self):
        """Return only fields used for remote subscription lookup."""
        if not self.is_valid():
            return {}
        allowed = (
            "subscription_identifier",
            "end_customer_name",
            "end_customer_site_id",
            "bill_to_id",
            "status",
            "from_date",
            "to_date",
        )
        return {key: value for key, value in self.cleaned_data.items() if key in allowed and value not in (None, "")}

    def cleaned_line_filters(self):
        """Return only client-side line filters."""
        if not self.is_valid():
            return {}
        allowed = ("pak_serial_number", "so_mso_number", "po_mpo_number", "line_end_customer")
        return {key: value for key, value in self.cleaned_data.items() if key in allowed and value not in (None, "")}

    def selected_environment(self):
        """Return the selected environment."""
        if not self.is_valid():
            return None
        return self.cleaned_data["environment"]
