"""Models for Nautobot Software Lifecycle."""

# Django imports
from django.db import models

# Nautobot imports
from nautobot.apps.constants import CHARFIELD_MAX_LENGTH
from nautobot.apps.models import PrimaryModel, extras_features
from nautobot.tenancy.models import Tenant


@extras_features("custom_links", "custom_validators", "export_templates", "graphql", "webhooks")
class SoftwareLicense(PrimaryModel):  # pylint: disable=too-many-ancestors
    """Model for tracking software licenses and their lifecycle."""

    # Tenant relationship
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="software_licenses",
        help_text="Tenant associated with this license"
    )

    # Core identification fields
    serial_number_pak = models.CharField(
        max_length=CHARFIELD_MAX_LENGTH,
        blank=True,
        null=True,
        verbose_name="Serial Number / PAK number"
    )
    product_id = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)
    product_description = models.TextField(blank=True)

    # Coverage fields
    coverage = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)
    covered_line_status = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)

    # Business Entity fields
    business_entity = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)
    sub_business_entity = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)

    # Product information
    product_family = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)
    asset_type = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)
    product_type = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)
    buying_program = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)
    offer_type = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)
    parent_offer_type = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)
    pid_mapping_group = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)

    # Quantity
    item_quantity = models.IntegerField(blank=True, null=True)

    # Date fields
    covered_line_start_date = models.DateField(blank=True, null=True)
    covered_line_end_date = models.DateField(blank=True, null=True)
    covered_line_end_date_fy = models.CharField(max_length=50, blank=True)
    covered_line_end_date_fy_fq = models.CharField(max_length=50, blank=True)
    ship_date = models.DateField(blank=True, null=True)
    ship_date_fy = models.CharField(max_length=50, blank=True)
    ship_date_fy_fq = models.CharField(max_length=50, blank=True)
    end_of_product_sale_date = models.DateField(blank=True, null=True)
    last_renewal_date = models.DateField(blank=True, null=True)
    end_of_software_maintenance_date = models.DateField(blank=True, null=True)
    last_date_of_support = models.DateField(blank=True, null=True)
    ldos_fy = models.CharField(max_length=50, blank=True, verbose_name="LDOS FY")
    ldos_fy_fq = models.CharField(max_length=50, blank=True, verbose_name="LDOS FY-FQ")

    # Contract fields
    contract_type = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)
    service_brand_code = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)
    contract_number = models.BigIntegerField(blank=True, null=True)
    subscription_id = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)

    # Migration and EOL fields
    migration_pid_flag = models.CharField(max_length=50, blank=True)
    end_of_life_product_bulletin = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)

    # MSS Extended Support fields
    mss_extended_support_assessment_result = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)
    mss_extended_support_end_date = models.DateField(blank=True, null=True)
    mss_extended_support_approved_service_level = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)

    # Warranty fields
    warranty_type = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)
    warranty_end_date = models.DateField(blank=True, null=True)

    # Install Site fields
    install_site_gu_name = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)
    install_site_gu_id = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)
    install_site_cr_parent_party_name = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)
    install_site_cr_parent_party_id = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)
    install_site_cr_party_name = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)
    install_site_cr_party_id = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)
    install_site_name = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)
    install_site_id = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)
    install_site_address_1 = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)
    install_site_city = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)
    install_site_state = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)
    install_site_country = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)
    install_site_postal_code = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)

    # Partner fields
    best_partner_be_geo_id = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)
    best_partner_be_geo_name = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)
    product_bill_to_id = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)
    product_bill_to_partner_name = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)
    product_partner_be_geo_id = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)
    product_partner_be_geo_name = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)
    pos_partner_be_geo_id = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)
    pos_partner_be_geo_name = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)
    service_bill_to_id = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)
    service_bill_to_partner_name = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)
    service_partner_be_geo_id = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)
    service_partner_be_geo_name = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)

    # Service level
    default_service_level = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)

    # Instance and Order fields
    instance_id = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)
    parent_instance_id = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)
    product_so = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)
    product_po = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)
    service_so = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)
    service_po = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)
    web_order_id = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)

    # Status and eligibility fields
    mapped_to_swss = models.CharField(max_length=10, blank=True, verbose_name="Mapped to SWSS (Y/N)")
    auto_renewal_flag = models.CharField(max_length=10, blank=True)
    installed_base_status = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)
    atr_eligible = models.CharField(max_length=10, blank=True)
    do_not_renew_reason = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)
    intended_use = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)
    st_eligible = models.CharField(max_length=10, blank=True)
    st_current = models.CharField(max_length=10, blank=True)

    # License fields
    license_product_id = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)
    ela_yorn = models.CharField(max_length=10, blank=True, verbose_name="ELA Y/N")

    # Field Notice fields
    field_notice = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)
    field_notice_title = models.TextField(blank=True)
    major_minor = models.CharField(max_length=50, blank=True)

    # Configuration
    configuration = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)

    class Meta:
        """Meta class."""

        ordering = ["tenant", "product_id"]
        verbose_name = "Software License"
        verbose_name_plural = "Software Licenses"

    def __str__(self):
        """Stringify instance."""
        return f"{self.product_id} - {self.tenant.name if self.tenant else 'No Tenant'}"
