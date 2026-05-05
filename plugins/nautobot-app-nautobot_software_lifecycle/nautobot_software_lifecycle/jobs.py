"""Jobs for Nautobot Software Lifecycle."""

from datetime import datetime
import pandas as pd
from io import BytesIO

from nautobot.apps.jobs import Job, FileVar, ObjectVar, register_jobs
from nautobot.tenancy.models import Tenant

from .models import SoftwareLicense


class ImportSoftwareLicensesJob(Job):
    """Job to import software licenses from Excel file."""

    class Meta:
        """Metadata for the job."""

        name = "Import Software Licenses from Excel"
        description = "Import software license data from an Excel file, filtering for SOFTWARE product types only"
        has_sensitive_variables = False

    excel_file = FileVar(
        description="Excel file containing software license data",
        required=True
    )

    tenant = ObjectVar(
        description="Tenant to associate with imported licenses",
        model=Tenant,
        required=True
    )

    def run(self, excel_file, tenant):
        """Execute the job."""
        self.logger.info(f"Starting import for tenant: {tenant.name}")

        # Read Excel file
        try:
            df = pd.read_excel(BytesIO(excel_file.read()))
            self.logger.info(f"Excel file loaded successfully. Total rows: {len(df)}")
        except Exception as e:
            self.logger.error(f"Failed to read Excel file: {str(e)}")
            return

        # Filter for SOFTWARE product type only
        df_software = df[df['Product Type'] == 'SOFTWARE'].copy()
        self.logger.info(f"Filtered to SOFTWARE products only. Rows: {len(df_software)}")

        if len(df_software) == 0:
            self.logger.warning("No SOFTWARE products found in the Excel file")
            return

        # Track statistics
        created_count = 0
        updated_count = 0
        error_count = 0

        # Process each row
        for idx, row in df_software.iterrows():
            try:
                # Helper function to safely get date values
                def parse_date(value):
                    """Parse date value from Excel."""
                    if pd.isna(value):
                        return None
                    if isinstance(value, datetime):
                        return value.date()
                    try:
                        return pd.to_datetime(value).date()
                    except:
                        return None

                # Helper function to safely get string values
                def safe_str(value, max_length=255):
                    """Safely convert value to string."""
                    if pd.isna(value):
                        return ""
                    return str(value)[:max_length]

                # Helper function to safely get integer values
                def safe_int(value):
                    """Safely convert value to integer."""
                    if pd.isna(value):
                        return None
                    try:
                        return int(value)
                    except:
                        return None

                # Map Excel columns to model fields
                license_data = {
                    'tenant': tenant,
                    'serial_number_pak': safe_str(row.get('Serial Number / PAK number')),
                    'coverage': safe_str(row.get('Coverage')),
                    'covered_line_status': safe_str(row.get('Covered Line Status')),
                    'business_entity': safe_str(row.get('Business Entity')),
                    'sub_business_entity': safe_str(row.get('Sub Business Entity')),
                    'product_family': safe_str(row.get('Product Family')),
                    'product_id': safe_str(row.get('Product ID')),
                    'product_description': safe_str(row.get('Product Description'), max_length=5000),
                    'asset_type': safe_str(row.get('Asset Type')),
                    'product_type': safe_str(row.get('Product Type')),
                    'buying_program': safe_str(row.get('Buying Program')),
                    'offer_type': safe_str(row.get('Offer Type')),
                    'parent_offer_type': safe_str(row.get('Parent Offer Type')),
                    'pid_mapping_group': safe_str(row.get('PID Mapping Group')),
                    'item_quantity': safe_int(row.get('Item Quantity')),
                    'covered_line_start_date': parse_date(row.get('Covered Line Start Date')),
                    'covered_line_end_date': parse_date(row.get('Covered Line End Date')),
                    'covered_line_end_date_fy': safe_str(row.get('Covered Line End Date FY'), 50),
                    'covered_line_end_date_fy_fq': safe_str(row.get('Covered Line End Date FY-FQ'), 50),
                    'contract_type': safe_str(row.get('Contract Type')),
                    'service_brand_code': safe_str(row.get('Service Brand Code')),
                    'contract_number': safe_int(row.get('Contract Number')),
                    'subscription_id': safe_str(row.get('Subscription ID')),
                    'ship_date': parse_date(row.get('Ship Date')),
                    'ship_date_fy': safe_str(row.get('Ship Date FY'), 50),
                    'ship_date_fy_fq': safe_str(row.get('Ship Date FY-FQ'), 50),
                    'end_of_product_sale_date': parse_date(row.get('End of Product Sale Date')),
                    'last_renewal_date': parse_date(row.get('Last Renewal Date')),
                    'end_of_software_maintenance_date': parse_date(row.get('End of Software Maintenance Date')),
                    'last_date_of_support': parse_date(row.get('Last Date of Support')),
                    'ldos_fy': safe_str(row.get('LDOS FY'), 50),
                    'ldos_fy_fq': safe_str(row.get('LDOS FY-FQ'), 50),
                    'migration_pid_flag': safe_str(row.get('Migration PID Flag'), 50),
                    'end_of_life_product_bulletin': safe_str(row.get('End Of Life Product Bulletin')),
                    'mss_extended_support_assessment_result': safe_str(row.get('MSS Extended Support Assessment Result')),
                    'mss_extended_support_end_date': parse_date(row.get('MSS Extended Support End Date')),
                    'mss_extended_support_approved_service_level': safe_str(row.get('MSS Extended Support Approved Service Level')),
                    'warranty_type': safe_str(row.get('Warranty Type')),
                    'warranty_end_date': parse_date(row.get('Warranty End Date')),
                    'install_site_gu_name': safe_str(row.get('Install Site GU Name')),
                    'install_site_gu_id': safe_str(row.get('Install Site GU ID')),
                    'install_site_cr_parent_party_name': safe_str(row.get('Install Site CR Parent Party Name')),
                    'install_site_cr_parent_party_id': safe_str(row.get('Install Site CR Parent Party ID')),
                    'install_site_cr_party_name': safe_str(row.get('Install Site CR Party Name')),
                    'install_site_cr_party_id': safe_str(row.get('Install Site CR Party ID')),
                    'install_site_name': safe_str(row.get('Install Site Name')),
                    'install_site_id': safe_str(row.get('Install Site ID')),
                    'install_site_address_1': safe_str(row.get('Install Site Address 1')),
                    'install_site_city': safe_str(row.get('Install Site City')),
                    'install_site_state': safe_str(row.get('Install Site State')),
                    'install_site_country': safe_str(row.get('Install Site Country')),
                    'install_site_postal_code': safe_str(row.get('Install Site Postal Code')),
                    'best_partner_be_geo_id': safe_str(row.get('Best Partner BE GEO ID')),
                    'best_partner_be_geo_name': safe_str(row.get('Best Partner BE GEO Name')),
                    'product_bill_to_id': safe_str(row.get('Product Bill to ID')),
                    'product_bill_to_partner_name': safe_str(row.get('Product Bill to Partner Name')),
                    'product_partner_be_geo_id': safe_str(row.get('Product Partner BE GEO ID')),
                    'product_partner_be_geo_name': safe_str(row.get('Product Partner BE GEO Name')),
                    'pos_partner_be_geo_id': safe_str(row.get('POS Partner BE GEO ID')),
                    'pos_partner_be_geo_name': safe_str(row.get('POS Partner BE GEO Name')),
                    'service_bill_to_id': safe_str(row.get('Service Bill to ID')),
                    'service_bill_to_partner_name': safe_str(row.get('Service Bill to Partner Name')),
                    'service_partner_be_geo_id': safe_str(row.get('Service Partner BE GEO ID')),
                    'service_partner_be_geo_name': safe_str(row.get('Service Partner BE GEO Name')),
                    'default_service_level': safe_str(row.get('Default Service Level')),
                    'instance_id': safe_str(row.get('Instance ID')),
                    'parent_instance_id': safe_str(row.get('Parent Instance ID')),
                    'product_so': safe_str(row.get('Product SO')),
                    'product_po': safe_str(row.get('Product PO')),
                    'service_so': safe_str(row.get('Service SO')),
                    'service_po': safe_str(row.get('Service PO')),
                    'web_order_id': safe_str(row.get('Web Order ID')),
                    'mapped_to_swss': safe_str(row.get('Mapped to SWSS (Y/N)'), 10),
                    'auto_renewal_flag': safe_str(row.get('Auto-renewal flag'), 10),
                    'installed_base_status': safe_str(row.get('Installed Base Status')),
                    'atr_eligible': safe_str(row.get('ATR Eligible'), 10),
                    'do_not_renew_reason': safe_str(row.get('Do Not Renew Reason')),
                    'intended_use': safe_str(row.get('Intended Use')),
                    'st_eligible': safe_str(row.get('ST Eligible'), 10),
                    'st_current': safe_str(row.get('ST current'), 10),
                    'license_product_id': safe_str(row.get('License Product ID')),
                    'ela_yorn': safe_str(row.get('ELA Yorn'), 10),
                    'field_notice': safe_str(row.get('Field Notice')),
                    'field_notice_title': safe_str(row.get('Field Notice Title'), max_length=5000),
                    'major_minor': safe_str(row.get('Major/Minor'), 50),
                    'configuration': safe_str(row.get('Configuration')),
                }

                # Create or update license record
                # Use a combination of tenant, product_id, and contract_number as unique identifier
                product_id = license_data['product_id']
                contract_number = license_data['contract_number']

                if product_id and contract_number:
                    license, created = SoftwareLicense.objects.update_or_create(
                        tenant=tenant,
                        product_id=product_id,
                        contract_number=contract_number,
                        defaults=license_data
                    )
                else:
                    # If no unique identifiers, just create
                    license = SoftwareLicense.objects.create(**license_data)
                    created = True

                if created:
                    created_count += 1
                    self.logger.debug(f"Created license: {license}")
                else:
                    updated_count += 1
                    self.logger.debug(f"Updated license: {license}")

            except Exception as e:
                error_count += 1
                self.logger.error(f"Error processing row {idx}: {str(e)}")
                continue

        # Log summary
        self.logger.info(f"Import completed:")
        self.logger.info(f"  - Created: {created_count}")
        self.logger.info(f"  - Updated: {updated_count}")
        self.logger.info(f"  - Errors: {error_count}")
        self.logger.info(f"  - Total processed: {created_count + updated_count}")


register_jobs(ImportSoftwareLicensesJob)
