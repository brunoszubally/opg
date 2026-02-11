#!/usr/bin/env python3
"""
Export invoices excluding STORNO invoices AND their original pairs

This script removes:
1. STORNO invoices
2. The original invoices that were stornoed (matched by amount and date)
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


def find_and_remove_storno_pairs(invoices: List[Dict[str, Any]], year: int) -> tuple:
    """
    Find STORNO invoices and their original pairs, remove both

    Returns:
        (filtered_invoices, storno_count, original_count)
    """
    # Separate STORNO and regular invoices
    storno_invoices = []
    regular_invoices = []

    for invoice in invoices:
        operation = invoice.get('invoiceOperation', 'CREATE')
        if operation == 'STORNO':
            storno_invoices.append(invoice)
        else:
            regular_invoices.append(invoice)

    logger.info(f"Found {len(storno_invoices)} STORNO invoices")
    logger.info(f"Found {len(regular_invoices)} regular invoices")

    # For each STORNO, try to find its original invoice
    # Match by: amount (absolute value) and delivery date
    matched_originals = set()
    unmatched_stornos = []

    for storno in storno_invoices:
        storno_amount = abs(float(storno.get('invoiceNetAmountHUF', 0)))
        storno_delivery_date = storno.get('invoiceDeliveryDate', '')
        storno_number = storno.get('invoiceNumber', '')

        # Try to find matching original
        found_match = False
        for i, original in enumerate(regular_invoices):
            if i in matched_originals:
                continue

            original_amount = abs(float(original.get('invoiceNetAmountHUF', 0)))
            original_delivery_date = original.get('invoiceDeliveryDate', '')
            original_number = original.get('invoiceNumber', '')

            # Match by amount and delivery date
            if (abs(storno_amount - original_amount) < 0.01 and
                storno_delivery_date == original_delivery_date):

                logger.info(f"  PAIR: STORNO {storno_number} ({storno_amount} Ft) <-> ORIGINAL {original_number} ({original_amount} Ft)")
                matched_originals.add(i)
                found_match = True
                break

        if not found_match:
            logger.warning(f"  UNPAIRED STORNO: {storno_number} ({storno_amount} Ft, {storno_delivery_date}) - no matching original found")
            unmatched_stornos.append(storno)

    # Keep only invoices that were NOT matched
    filtered_invoices = [
        inv for i, inv in enumerate(regular_invoices)
        if i not in matched_originals
    ]

    logger.info(f"\nRemoved {len(storno_invoices)} STORNO invoices")
    logger.info(f"Removed {len(matched_originals)} original invoices (matched pairs)")
    logger.info(f"Unmatched STORNOs (kept as warning): {len(unmatched_stornos)}")
    logger.info(f"Remaining invoices: {len(filtered_invoices)}")

    return filtered_invoices, len(storno_invoices), len(matched_originals)


def export_invoices_without_storno_pairs(
    login: str,
    password: str,
    tax_number: str,
    sign_key: str,
    exchange_key: str,
    year: int,
    output_file: str
) -> None:
    """
    Export invoices excluding STORNO pairs
    """
    logger.info(f"Starting invoice export for year {year} (excluding STORNO pairs)...")

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

    # Query invoices by ISSUE date
    logger.info(f"Fetching all invoices for year {year}...")
    all_invoices = []

    import calendar
    from datetime import datetime, timedelta

    start_date = datetime(year, 1, 1)
    end_date = datetime(year + 1, 2, 28)

    current_date = start_date
    while current_date <= end_date:
        date_from = current_date.strftime("%Y-%m-%d")
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

        current_date = window_end + timedelta(days=1)

    logger.info(f"Total invoices fetched: {len(all_invoices)}")

    # Filter by delivery date
    filtered_invoices = []
    for invoice in all_invoices:
        delivery_date = invoice.get('invoiceDeliveryDate', '')
        if delivery_date and delivery_date.startswith(str(year)):
            filtered_invoices.append(invoice)

    logger.info(f"Invoices with delivery date in {year}: {len(filtered_invoices)}")

    # Find and remove STORNO pairs
    logger.info("\nFinding STORNO pairs...")
    final_invoices, storno_count, original_count = find_and_remove_storno_pairs(filtered_invoices, year)

    if not final_invoices:
        logger.warning("No invoices found after filtering")
        return

    # Prepare data for Excel
    excel_data = []

    for invoice in final_invoices:
        invoice_number = invoice.get('invoiceNumber', 'N/A')
        net_amount = float(invoice.get('invoiceNetAmountHUF', 0))
        operation = invoice.get('invoiceOperation', 'CREATE')
        issue_date = invoice.get('invoiceIssueDate', 'N/A')
        delivery_date = invoice.get('invoiceDeliveryDate', 'N/A')
        customer_name = invoice.get('customerName', 'N/A')

        # Add operation indicator
        if operation == 'MODIFY':
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
    df = df.sort_values('Teljesítés dátuma')

    # Calculate totals
    total_net = df['Nettó összeg (HUF)'].sum()

    logger.info(f"\nExporting {len(df)} invoices to {output_file}...")

    # Export to Excel
    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name=f'Számlák {year}', index=False)

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

        from openpyxl.styles import Font
        worksheet[f'A{total_row}'].font = Font(bold=True)
        worksheet[f'B{total_row}'].font = Font(bold=True)

        # Format currency column
        for row in range(2, total_row + 1):
            cell = worksheet[f'B{row}']
            cell.number_format = '#,##0.00'

    logger.info(f"✓ Successfully exported to {output_file}")
    logger.info(f"  Total invoices: {len(df)}")
    logger.info(f"  Excluded STORNO invoices: {storno_count}")
    logger.info(f"  Excluded original pairs: {original_count}")
    logger.info(f"  Total net amount: {total_net:,.2f} HUF")


def main():
    parser = argparse.ArgumentParser(
        description='Export NAV Online Invoices excluding STORNO pairs'
    )

    parser.add_argument('--login', required=True)
    parser.add_argument('--password', required=True)
    parser.add_argument('--tax-number', required=True)
    parser.add_argument('--sign-key', required=True)
    parser.add_argument('--exchange-key', required=True)
    parser.add_argument('--year', type=int, default=datetime.now().year)
    parser.add_argument('--output', default=None)

    args = parser.parse_args()

    if not args.output:
        args.output = f'szamlak_{args.tax_number}_{args.year}_clean.xlsx'

    try:
        export_invoices_without_storno_pairs(
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
