#!/usr/bin/env python3
"""
Export all NAV Online Invoices to Excel

This script downloads all invoices for the current year and exports them to an Excel file
with columns: Invoice Name, Net Amount (HUF)
"""

import logging
import sys
from datetime import datetime
from typing import List, Dict, Any
import argparse

try:
    import pandas as pd
except ImportError:
    print("ERROR: pandas is not installed. Please run: pip install pandas openpyxl")
    sys.exit(1)

from nav_online_invoice import (
    NavOnlineInvoiceConfig,
    NavOnlineInvoiceReporter,
    normalize_tax_number
)
from online_invoice_api import query_all_invoices_paginated

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def export_invoices_to_excel(
    login: str,
    password: str,
    tax_number: str,
    sign_key: str,
    exchange_key: str,
    year: int,
    output_file: str
) -> None:
    """
    Export all invoices to Excel file

    Args:
        login: NAV technical user login
        password: NAV password
        tax_number: Tax number (will be normalized to 8 digits)
        sign_key: Signing key
        exchange_key: Exchange key
        year: Year to export
        output_file: Output Excel file path
    """

    logger.info(f"Starting invoice export for year {year}...")

    # Normalize tax number
    normalized_tax = normalize_tax_number(tax_number)
    if not normalized_tax:
        logger.error(f"Invalid tax number: {tax_number}")
        return

    logger.info(f"Normalized tax number: {normalized_tax}")

    # Build credentials
    user_data = {
        "login": login,
        "password": password,
        "taxNumber": normalized_tax,
        "signKey": sign_key,
        "exchangeKey": exchange_key
    }

    software_data = {
        "softwareId": "123456789123456789",
        "softwareName": "Invoice Exporter",
        "softwareOperation": "ONLINE_SERVICE",
        "softwareMainVersion": "1.0",
        "softwareDevName": "Szubally Bruno",
        "softwareDevContact": "info@example.com",
        "softwareDevCountryCode": "HU",
        "softwareDevTaxNumber": "12345678"
    }

    # Create NAV client
    logger.info("Creating NAV Online Invoice client...")
    config = NavOnlineInvoiceConfig(NavOnlineInvoiceConfig.PROD_URL, user_data, software_data)
    reporter = NavOnlineInvoiceReporter(config)
    logger.info("NAV client created successfully")

    # Query invoices by ISSUE date (NAV API limit: 35 days max per query)
    # We'll fetch a wider range (year + 2 months after) to catch invoices issued in next year
    # but with delivery date in target year
    logger.info(f"Fetching all invoices for year {year} (by issue date, will filter by delivery date)...")
    all_invoices = []

    # Fetch from year start to 2 months into next year
    import calendar
    from datetime import datetime, timedelta

    start_date = datetime(year, 1, 1)
    end_date = datetime(year + 1, 2, 28)  # Include Jan + Feb of next year

    current_date = start_date
    while current_date <= end_date:
        date_from = current_date.strftime("%Y-%m-%d")

        # Calculate 30 days window (to stay under 35 day limit)
        window_end = current_date + timedelta(days=30)
        if window_end > end_date:
            window_end = end_date
        date_to = window_end.strftime("%Y-%m-%d")

        logger.info(f"  Fetching {date_from} to {date_to}...")

        invoice_query_params = {
            "mandatoryQueryParams": {
                "invoiceIssueDate": {
                    "dateFrom": date_from,
                    "dateTo": date_to,
                },
            },
        }

        monthly_invoices = query_all_invoices_paginated(reporter, invoice_query_params)
        logger.info(f"    Found {len(monthly_invoices)} invoices")
        all_invoices.extend(monthly_invoices)

        # Move to next window
        current_date = window_end + timedelta(days=1)

    logger.info(f"Total invoices fetched (before delivery date filter): {len(all_invoices)}")

    # Filter by delivery date (only keep invoices with delivery date in target year)
    filtered_invoices = []
    for invoice in all_invoices:
        delivery_date = invoice.get('invoiceDeliveryDate', '')
        if delivery_date and delivery_date.startswith(str(year)):
            filtered_invoices.append(invoice)

    logger.info(f"Invoices with delivery date in {year}: {len(filtered_invoices)}")
    all_invoices = filtered_invoices

    if not all_invoices:
        logger.warning("No invoices found for the specified period")
        return

    # Prepare data for Excel
    excel_data = []

    for invoice in all_invoices:
        invoice_number = invoice.get('invoiceNumber', 'N/A')
        net_amount = float(invoice.get('invoiceNetAmountHUF', 0))
        operation = invoice.get('invoiceOperation', 'CREATE')
        issue_date = invoice.get('invoiceIssueDate', 'N/A')
        delivery_date = invoice.get('invoiceDeliveryDate', 'N/A')
        customer_name = invoice.get('customerName', 'N/A')

        # Add operation indicator to invoice number
        if operation == 'STORNO':
            invoice_number = f"{invoice_number} (STORNÓ)"
            net_amount = -abs(net_amount)  # Negative for storno
        elif operation == 'MODIFY':
            invoice_number = f"{invoice_number} (MÓDOSÍTÓ)"

        excel_data.append({
            'Számla száma': invoice_number,
            'Nettó összeg (HUF)': net_amount,
            'Teljesítés dátuma': delivery_date,
            'Kiállítás dátuma': issue_date,
            'Vevő neve': customer_name,
            'Művelet': operation
        })

    # Create DataFrame
    df = pd.DataFrame(excel_data)

    # Sort by delivery date
    df = df.sort_values('Teljesítés dátuma')

    # Calculate totals
    total_net = df['Nettó összeg (HUF)'].sum()

    logger.info(f"Exporting {len(df)} invoices to {output_file}...")

    # Export to Excel with formatting
    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name=f'Számlák {year}', index=False)

        # Get worksheet
        worksheet = writer.sheets[f'Számlák {year}']

        # Auto-adjust column widths
        for column in worksheet.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 50)
            worksheet.column_dimensions[column_letter].width = adjusted_width

        # Add totals row
        total_row = len(df) + 2
        worksheet[f'A{total_row}'] = 'ÖSSZESEN:'
        worksheet[f'B{total_row}'] = total_net
        worksheet[f'A{total_row}'].font = worksheet[f'A{total_row}'].font.copy(bold=True)
        worksheet[f'B{total_row}'].font = worksheet[f'B{total_row}'].font.copy(bold=True)

        # Format currency column
        for row in range(2, total_row + 1):
            cell = worksheet[f'B{row}']
            cell.number_format = '#,##0.00'

    logger.info(f"✓ Successfully exported to {output_file}")
    logger.info(f"  Total invoices: {len(df)}")
    logger.info(f"  Total net amount: {total_net:,.2f} HUF")


def main():
    parser = argparse.ArgumentParser(
        description='Export NAV Online Invoices to Excel',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Export with credentials from image
  python3 export_invoices_to_excel.py \\
    --login gcuqetuk4jjulft \\
    --password "Bruni1998!" \\
    --tax-number 32773877 \\
    --sign-key "ed-8633-646a2fc3932a58YF2KN7EWJK" \\
    --exchange-key "528358YF2KN7ED5G" \\
    --year 2025 \\
    --output szamlak_2025.xlsx

  # Export current year (default)
  python3 export_invoices_to_excel.py \\
    --login gcuqetuk4jjulft \\
    --password "Bruni1998!" \\
    --tax-number 32773877 \\
    --sign-key "ed-8633-646a2fc3932a58YF2KN7EWJK" \\
    --exchange-key "528358YF2KN7ED5G"
        """
    )

    parser.add_argument('--login', required=True, help='NAV technical user login')
    parser.add_argument('--password', required=True, help='NAV password')
    parser.add_argument('--tax-number', required=True, help='Tax number (8 digits)')
    parser.add_argument('--sign-key', required=True, help='Signing key (with dashes)')
    parser.add_argument('--exchange-key', required=True, help='Exchange key')
    parser.add_argument('--year', type=int, default=datetime.now().year, help='Year to export (default: current year)')
    parser.add_argument('--output', default=None, help='Output Excel file (default: szamlak_YYYY.xlsx)')

    args = parser.parse_args()

    # Default output filename
    if not args.output:
        args.output = f'szamlak_{args.year}.xlsx'

    try:
        export_invoices_to_excel(
            login=args.login,
            password=args.password,
            tax_number=args.tax_number,
            sign_key=args.sign_key,
            exchange_key=args.exchange_key,
            year=args.year,
            output_file=args.output
        )
    except Exception as ex:
        logger.error(f"Error: {str(ex)}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
