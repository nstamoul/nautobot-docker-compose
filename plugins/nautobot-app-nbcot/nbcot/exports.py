"""Excel exports for NBCOT tracked orders."""

from __future__ import annotations

from io import BytesIO
from typing import Iterable

from openpyxl import Workbook
from openpyxl.styles import Alignment
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import quote_sheetname
from openpyxl.worksheet.hyperlink import Hyperlink

from nbcot.cisco.line_items import build_line_tree
from nbcot.cisco.serials import joined_attribute_values


ORDER_HEADERS = [
    "Order Number",
    "Environment",
    "Customer PO Number",
    "Project Number",
    "Notes",
    "Account Name",
    "Account Number",
    "Status",
    "Status Detail",
    "Lifecycle State",
    "Is Tracked",
    "Is Archived",
    "Requested Delivery Date",
    "Promised Delivery Date",
    "Estimated Delivery Date",
    "Last Synced At",
    "Last Sync Status",
    "Notification Recipients",
    "Web Order URL",
    "Cisco Sales Order URL",
]

LINE_HEADERS = [
    "Order Number",
    "Line Number",
    "Parent Line",
    "Line Key",
    "Classification",
    "SKU",
    "Description",
    "Status",
    "Shipment Status",
    "Serial Number",
    "Parent Serial Number",
    "MAC Address",
    "IMEI Number",
    "Instance Number",
    "License Key",
    "Cloud ID",
    "Contract Number",
    "Carrier",
    "Tracking Number",
    "Tracking URL",
    "Proof Of Delivery URL",
    "Quantity Ordered",
    "Quantity Fulfilled",
    "Quantity Backordered",
    "Promised Delivery Date",
    "Estimated Delivery Date",
    "Actual Delivery Date",
    "Estimated Ship Date",
    "Is Tracked",
]

CISCO_LINE_HEADERS = [
    "Line Number",
    "Item Name",
    "True Forward",
    "Item Description",
    "Reason Code",
    "ECO Number",
    "PO Line Reference",
    "Line Status",
    "Ship Date",
    "Recommitted Date",
    "Start Date",
    "End Date",
    "Serial Numbers",
    "Service/ Subscription Start Date",
    "Service Duration",
    "PAK",
    "Ship Set#",
    "List Price",
    "Quantity Ordered",
    "Quantity Shipped",
    "Extended List Price",
    "Special Sales Trade Program Compliant",
    "TAA",
    "Discount %",
    "Discount Amount",
    "Credits",
    "Unit Net Price",
    "Extended Net Price",
    "Delivery Options",
    "Specific Delivery Time",
    "Authorized Receiving Party",
    "Carier Will Call",
    "Remove Packaging",
    "Contact Prior To Delivery",
    "Inside Delivery",
    "Pre-shippment Inspection",
    "Special Transport",
    "Country of Origin Certificate Provided by Cisco",
    "Certificate of Origin Purchased",
    "Invoice Number",
    "Invoice Date",
    "Invoice Type",
    "Ship Set Status",
    "Service Level",
    "Total weight",
    "Shipping Cost",
    "Carrier Account #",
    "Carrier",
    "Freight Term",
    "Warehouse Information/Ship From Location",
    "Duty",
    "Request Date",
    "Tracking Number",
    "Carton Id",
    "Country of Origin",
    "Carton Weight",
    "Scheduled Ship Date",
    "Scheduled Install Date",
    "Scheduled Delivery Date",
    "Actual Ship Date",
    "Actual Delivery Date",
    "Status Completed Date",
    "Received By",
    "Service Covered Product",
    "Actual Contract Number",
    "Request Contract Number",
    "Service Date Range",
    "Shipping Site Contact Name",
    "Shipping Site Address Line 1",
    "Shipping Site Address Line 2",
    "Shipping Site Address Line 3",
    "Shipping Site Address Line 4",
    "Shipping Site City",
    "Shipping Site State",
    "Shipping Site County",
    "Shipping Site Country/Region",
    "Shipping Site Zip",
    "Shipping Site Contact Email",
    "Shipping Site Contact Fax",
    "Shipping Site Contact Telephone",
    "Install Site Contact Name",
    "Install Site Address Line 1",
    "Install Site Address Line 2",
    "Install Site Address Line 3",
    "Install Site Address Line 4",
    "Install Site City",
    "Install Site State",
    "Install Site County",
    "Install Site Country/Region",
    "Install Site Zip",
    "Install Site Contact Email",
    "Install Site Contact Fax",
    "Install Site Contact Telephone",
    "End Customer Name",
    "End Customer Address Line 1",
    "End Customer Address Line 2",
    "End Customer Address Line 3",
    "End Customer Address Line 4",
    "End Customer City",
    "End Customer State",
    "End Customer County",
    "End Customer Country/Region",
    "End Customer Zip",
    "End Customer Email",
    "End Customer Fax",
    "End Customer Telephone",
    "Dist. Center Location",
    "Hand Over Point",
    "Cartons in Set",
    "Final Delivery Location",
    "House Airway",
    "Master Airway",
    "Flight Number",
    "Departure Date",
    "Arrival Date",
    "Terms (Initial-Renewal)",
    "Billing Model",
    "Charge Type",
    "Charge Frequency",
    "True up Term",
    "Requested Start Date",
    "Estimated Service/ Subscription Start Date",
    "Subscription Start Date",
    "Subscription End Date",
    "Subscription ID",
    "Estimated Delivery Date",
    "Actual Delivery Date",
    "Deposit Amount",
    "Consolidation Set",
    "Logistic Services",
    "Total Logistic Charges",
    "Freight Payer Contact Name",
    "Freight Payer Address Line 1",
    "Freight Payer Address Line 2",
    "Freight Payer Address Line 3",
    "Freight Payer Address Line 4",
    "Freight Payer City",
    "Freight Payer State",
    "Freight Payer County",
    "Freight Payer Country/Region",
    "Freight Payer Zip",
    "Freight Payer Contact Email",
    "Freight Payer Contact Fax",
    "Freight Payer Contact Telephone",
    "Proof of Delivery",
    "Delivery Exception Message",
    "Future Invoice Release Date",
    "Billing Amount",
    "MAGIC KEY",
    "Associated Service SKU",
    "License Provisioning Status",
    "Freight Eligible",
    "Capital Financing Frequency",
    "Reshipment Note",
    "Sales Tax Category",
    "Covered Product SO",
    "Covered Product Ship set",
    "Covered Product Ship Date",
    "Immediate Invoice",
    "Buying Program Motion",
    "BPA No Subscription Line",
    "Proof of Collection",
    "Year",
    "Milestone",
    "Solution Name",
    "Architecture",
    "CX Product",
    "Handover Date",
    "Marketplace Provider",
    "Marketplace Program",
]

NBCOT_EXTRA_LINE_HEADERS = [
    "MAC Addresses",
    "Parent Serial Numbers",
    "IMEI Number",
    "Instance Number",
    "License Key",
    "Cloud ID",
]


def _date_value(value):
    return value.isoformat() if value else ""


def _serial_export_value(line, property_name: str, field_name: str, fallback_attr: str) -> str:
    value = getattr(line, property_name, None)
    if value is not None:
        return value
    return joined_attribute_values(
        getattr(line, "raw_payload", {}),
        field_name,
        fallback=getattr(line, fallback_attr, ""),
    )


def _style_header(sheet):
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="4F81BD")


def _autosize(sheet):
    for column_cells in sheet.columns:
        width = max(len(str(cell.value or "")) for cell in column_cells) + 2
        sheet.column_dimensions[column_cells[0].column_letter].width = min(max(width, 12), 60)


def _wrap_multiline_cells(sheet):
    for row in sheet.iter_rows():
        for cell in row:
            if isinstance(cell.value, str) and "\n" in cell.value:
                cell.alignment = Alignment(wrap_text=True, vertical="top")


def _classification(row) -> str:
    return "Major" if row.depth == 0 else "Minor"


def _safe_sheet_title(order_number: str, used_titles: set[str]) -> str:
    """Return a valid, unique Excel sheet title based on an order number."""
    invalid_chars = set("[]:*?/\\")
    cleaned = "".join("-" if char in invalid_chars else char for char in str(order_number or "Order")).strip()
    cleaned = cleaned or "Order"
    base = cleaned[:31]
    title = base
    index = 2
    while title in used_titles:
        suffix = f"-{index}"
        title = f"{base[:31 - len(suffix)]}{suffix}"
        index += 1
    used_titles.add(title)
    return title


def _append_order_summary(orders_sheet, order, sheet_title: str):
    """Append one order to the summary sheet and link it to its detail sheet."""
    orders_sheet.append(
        [
            order.order_number,
            order.environment.upper(),
            order.customer_po_number,
            order.project_number,
            order.notes,
            order.account_name,
            order.account_number,
            order.status,
            order.status_detail,
            order.lifecycle_state,
            "Yes" if order.is_tracked else "No",
            "Yes" if order.is_archived else "No",
            _date_value(order.requested_delivery_date),
            _date_value(order.promised_delivery_date),
            _date_value(order.estimated_delivery_date),
            order.last_synced_at.isoformat() if order.last_synced_at else "",
            order.last_sync_status,
            order.notification_recipients,
            order.web_order_url,
            order.cisco_sales_order_url,
        ]
    )
    order_cell = orders_sheet.cell(row=orders_sheet.max_row, column=1)
    order_cell.hyperlink = Hyperlink(
        ref=order_cell.coordinate,
        location=f"{quote_sheetname(sheet_title)}!A1",
        display=str(order.order_number),
    )
    order_cell.style = "Hyperlink"


def _append_order_lines(sheet, order):
    """Append one order's line hierarchy to its detail sheet."""
    line_rows = build_line_tree(order.lines.all())
    line_by_row_id = {row.row_id: row.line for row in line_rows}
    for row in line_rows:
        line = row.line
        parent_line = ""
        if row.parent_id:
            parent = line_by_row_id.get(row.parent_id)
            if parent is not None:
                parent_line = parent.line_number
        sheet.append(
            [
                order.order_number,
                line.line_number,
                parent_line,
                line.line_key,
                _classification(row),
                line.sku,
                line.description,
                line.status,
                line.shipment_status,
                _serial_export_value(line, "serial_numbers_export", "serialNumber", "serial_number"),
                _serial_export_value(line, "parent_serial_numbers_export", "parentSerialNumber", "parent_serial_number"),
                _serial_export_value(line, "mac_addresses_export", "macAddresses", "mac_address"),
                line.imei_number,
                line.instance_number,
                line.license_key,
                line.cloud_id,
                line.contract_number,
                line.carrier,
                line.tracking_number,
                line.tracking_url,
                line.proof_of_delivery_url,
                line.quantity_ordered,
                line.quantity_fulfilled,
                line.quantity_backordered,
                _date_value(line.promised_delivery_date),
                _date_value(line.estimated_delivery_date),
                _date_value(line.actual_delivery_date),
                _date_value(line.estimated_ship_date),
                "Yes" if line.is_tracked else "No",
            ]
        )
        if line.is_tracked:
            for cell in sheet[sheet.max_row]:
                cell.fill = PatternFill("solid", fgColor="EAF4FF")


def _append_order_header_sheet(sheet, order):
    """Append Cisco-like order header rows."""
    rows = [
        ("Order Number", order.order_number),
        ("Order Name", order.project_number),
        ("Order Status", order.status),
        ("Web Order ID", order.web_order_url),
        ("Customer PO Number", order.customer_po_number),
        ("Account Name", order.account_name),
        ("Account Number", order.account_number),
        ("Requested Delivery Date", _date_value(order.requested_delivery_date)),
        ("Promised Delivery Date", _date_value(order.promised_delivery_date)),
        ("Estimated Delivery Date", _date_value(order.estimated_delivery_date)),
        ("Last Synced At", order.last_synced_at.isoformat() if order.last_synced_at else ""),
        ("Last Sync Status", order.last_sync_status),
        ("Cisco Sales Order URL", order.cisco_sales_order_url),
        ("Notes", order.notes),
    ]
    for label, value in rows:
        sheet.append([label, value])
    sheet["A1"].font = Font(bold=True)
    for cell in sheet["A"]:
        cell.font = Font(bold=True)


def _cisco_line_row(order, row, parent_line: str) -> list:
    """Return a Cisco-like Order Line Details row with NBCOT fields mapped where available."""
    line = row.line
    values = [""] * (len(CISCO_LINE_HEADERS) + len(NBCOT_EXTRA_LINE_HEADERS))
    values[0] = line.line_number
    values[1] = line.sku
    values[3] = line.description
    values[7] = line.status
    values[8] = _date_value(line.estimated_ship_date)
    values[9] = _date_value(line.estimated_delivery_date)
    values[12] = _serial_export_value(line, "serial_numbers_export", "serialNumber", "serial_number")
    values[16] = line.ship_set
    values[18] = line.quantity_ordered
    values[19] = line.quantity_fulfilled
    values[42] = line.shipment_status
    values[47] = line.carrier
    values[52] = line.tracking_number
    values[56] = _date_value(line.estimated_ship_date)
    values[58] = _date_value(line.estimated_delivery_date)
    values[59] = _date_value(line.actual_delivery_date)
    values[60] = _date_value(line.actual_delivery_date)
    values[64] = line.contract_number
    values[65] = line.contract_number
    values[144] = line.proof_of_delivery_url
    values[170] = _serial_export_value(line, "mac_addresses_export", "macAddresses", "mac_address")
    values[171] = _serial_export_value(line, "parent_serial_numbers_export", "parentSerialNumber", "parent_serial_number")
    values[172] = line.imei_number
    values[173] = line.instance_number
    values[174] = line.license_key
    values[175] = line.cloud_id
    if parent_line:
        values[155] = order.order_number
        values[156] = parent_line
    return values


def _append_cisco_like_order_lines(sheet, order):
    """Append Cisco-like order-line rows."""
    line_rows = build_line_tree(order.lines.all())
    line_by_row_id = {row.row_id: row.line for row in line_rows}
    for row in line_rows:
        parent_line = ""
        if row.parent_id:
            parent = line_by_row_id.get(row.parent_id)
            if parent is not None:
                parent_line = parent.line_number
        sheet.append(_cisco_line_row(order, row, parent_line))


def build_order_workbook(order) -> bytes:
    """Build a Cisco-like XLSX workbook for one Cisco order."""
    workbook = Workbook()
    header_sheet = workbook.active
    header_sheet.title = "Order Header"
    _append_order_header_sheet(header_sheet, order)

    line_sheet = workbook.create_sheet("Order Line Details")
    line_sheet.append(CISCO_LINE_HEADERS + NBCOT_EXTRA_LINE_HEADERS)
    _style_header(line_sheet)
    _append_cisco_like_order_lines(line_sheet, order)
    line_sheet.freeze_panes = "A2"
    _wrap_multiline_cells(line_sheet)
    _autosize(line_sheet)

    credit_sheet = workbook.create_sheet("Credit Breakdown")
    credit_sheet.append(["#", "Part Number", "Credit Name", "Credits"])
    _style_header(credit_sheet)
    credit_sheet.append(["", "", "", ""])

    _autosize(header_sheet)
    _autosize(credit_sheet)
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def build_orders_workbook(orders: Iterable) -> bytes:
    """Build an XLSX workbook for the supplied Cisco orders."""
    workbook = Workbook()
    orders_sheet = workbook.active
    orders_sheet.title = "Tracked Orders"
    orders_sheet.append(ORDER_HEADERS)
    _style_header(orders_sheet)

    used_titles = {orders_sheet.title}
    for order in orders:
        sheet_title = _safe_sheet_title(order.order_number, used_titles)
        _append_order_summary(orders_sheet, order, sheet_title)

        order_sheet = workbook.create_sheet(sheet_title)
        order_sheet.append(LINE_HEADERS)
        _style_header(order_sheet)
        _append_order_lines(order_sheet, order)
        _wrap_multiline_cells(order_sheet)
        _autosize(order_sheet)

    _autosize(orders_sheet)
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()
