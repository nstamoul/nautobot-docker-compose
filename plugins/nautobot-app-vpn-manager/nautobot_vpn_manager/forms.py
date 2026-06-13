"""Forms for the VPN manager app."""

from django import forms
from nautobot.tenancy.models import Tenant


class VpnStartForm(forms.Form):
    """Form for starting a tenant-scoped VPN slot."""

    tenant = forms.ModelChoiceField(
        queryset=Tenant.objects.order_by("name"),
        required=False,
        empty_label="Select tenant",
        help_text="Preferred source of truth for tenant-scoped VPN start.",
    )
    customer = forms.CharField(
        required=False,
        max_length=100,
        help_text="Optional explicit Vault customer profile name when no tenant is selected.",
    )
    worker_count = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=32,
        initial=1,
        help_text="Desired number of workers bound to the tenant VPN queue. Defaults to 1.",
    )
    otp = forms.CharField(required=False, max_length=64)
    authgroup = forms.CharField(required=False, max_length=128)
    banner_response = forms.CharField(required=False, max_length=128, initial="yes")
    extra_args = forms.CharField(required=False, max_length=512)
    passthrough = forms.CharField(required=False, max_length=512)

    def clean(self):
        cleaned = super().clean()
        tenant = cleaned.get("tenant")
        customer = (cleaned.get("customer") or "").strip()
        if tenant is None and not customer:
            raise forms.ValidationError("Select a tenant or provide a customer override.")
        return cleaned

    def resolved_customer(self) -> str:
        """Return the effective customer profile name."""
        tenant = self.cleaned_data.get("tenant")
        if tenant is not None:
            return tenant.name
        return (self.cleaned_data.get("customer") or "").strip()

    def resolved_worker_count(self) -> int:
        """Return the desired worker count."""
        return int(self.cleaned_data.get("worker_count") or 1)
