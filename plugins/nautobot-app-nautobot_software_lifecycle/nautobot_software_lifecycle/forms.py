"""Forms for nautobot_software_lifecycle."""

from django import forms
from nautobot.apps.constants import CHARFIELD_MAX_LENGTH
from nautobot.apps.forms import NautobotBulkEditForm, NautobotFilterForm, NautobotModelForm, TagsBulkEditFormMixin
from nautobot.tenancy.models import Tenant

from nautobot_software_lifecycle import models


class SoftwareLicenseForm(NautobotModelForm):  # pylint: disable=too-many-ancestors
    """SoftwareLicense creation/edit form."""

    class Meta:
        """Meta attributes."""

        model = models.SoftwareLicense
        fields = "__all__"


class SoftwareLicenseBulkEditForm(TagsBulkEditFormMixin, NautobotBulkEditForm):  # pylint: disable=too-many-ancestors
    """SoftwareLicense bulk edit form."""

    pk = forms.ModelMultipleChoiceField(
        queryset=models.SoftwareLicense.objects.all(),
        widget=forms.MultipleHiddenInput
    )
    tenant = forms.ModelChoiceField(queryset=Tenant.objects.all(), required=False)
    coverage = forms.CharField(required=False, max_length=CHARFIELD_MAX_LENGTH)
    product_type = forms.CharField(required=False, max_length=CHARFIELD_MAX_LENGTH)

    class Meta:
        """Meta attributes."""

        nullable_fields = [
            "coverage",
            "product_type",
        ]


class SoftwareLicenseFilterForm(NautobotFilterForm):
    """Filter form to filter searches."""

    model = models.SoftwareLicense
    field_order = ["q", "tenant", "product_id", "product_type", "coverage"]

    q = forms.CharField(
        required=False,
        label="Search",
        help_text="Search within Product ID, Product Description, or Contract Number.",
    )
    tenant = forms.ModelChoiceField(queryset=Tenant.objects.all(), required=False)
    product_id = forms.CharField(required=False, label="Product ID")
    product_type = forms.CharField(required=False, label="Product Type")
    coverage = forms.CharField(required=False, label="Coverage")
