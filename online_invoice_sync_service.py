"""
Online Invoice Sync Service

Syncs Online Invoice data to Adalo user records (monthly aggregations).
"""

import logging
from datetime import datetime
from typing import Dict, Any, Optional

from nav_online_invoice import (
    NavOnlineInvoiceConfig,
    NavOnlineInvoiceReporter
)
from online_invoice_api import (
    query_all_invoices_paginated,
    calculate_summary,
    HUNGARIAN_MONTHS,
    ENGLISH_MONTHS
)
from adalo_client import AdaloClient

logger = logging.getLogger(__name__)


def sync_online_invoice_for_user(user: Dict[str, Any], adalo_client: AdaloClient, year: int = None) -> Dict[str, Any]:
    """
    Sync Online Invoice data for a user and update user record with monthly aggregations

    Args:
        user: User dict from Adalo
        adalo_client: AdaloClient instance
        year: Year to sync (defaults to current year)

    Returns:
        Dict with sync result: {'success': bool, 'message': str, 'total_invoices': int, 'total_net': float}
    """
    if year is None:
        year = datetime.now().year

    user_id = user['id']

    # Check if user has Online Invoice credentials
    required_fields = ['navlogin', 'navpassword', 'signKey', 'exchangeKey', 'taxNumber']
    missing_fields = [f for f in required_fields if not user.get(f)]

    if missing_fields:
        return {
            'success': False,
            'message': f'Missing Online Invoice credentials: {", ".join(missing_fields)}',
            'total_invoices': 0,
            'total_net': 0.0
        }

    try:
        logger.info(f"Starting Online Invoice sync for user {user_id} (tax number: {user.get('taxNumber')})")

        # Build credentials
        user_data = {
            "login": user['navlogin'],
            "password": user['navpassword'],
            "taxNumber": user['taxNumber'],
            "signKey": user['signKey'],
            "exchangeKey": user['exchangeKey']
        }

        software_data = {
            "softwareId": "123456789123456789",
            "softwareName": "string",
            "softwareOperation": "ONLINE_SERVICE",
            "softwareMainVersion": "string",
            "softwareDevName": "string",
            "softwareDevContact": "string",
            "softwareDevCountryCode": "HU",
            "softwareDevTaxNumber": "string"
        }

        # Create NAV client
        config = NavOnlineInvoiceConfig(NavOnlineInvoiceConfig.PROD_URL, user_data, software_data)
        reporter = NavOnlineInvoiceReporter(config)

        # Prepare update data
        update_data = {
            'lastupdate': datetime.utcnow().isoformat() + 'Z'
        }

        total_invoices = 0
        total_net = 0.0

        # Query each month
        for month in range(1, 13):
            date_from = f"{year}-{month:02d}-01"
            # Get last day of month
            if month == 12:
                date_to = f"{year}-12-31"
            else:
                import calendar
                last_day = calendar.monthrange(year, month)[1]
                date_to = f"{year}-{month:02d}-{last_day:02d}"

            month_name = ENGLISH_MONTHS[month]
            logger.info(f"  Querying {month_name} ({date_from} to {date_to})...")

            try:
                invoice_query_params = {
                    "mandatoryQueryParams": {
                        "invoiceIssueDate": {
                            "dateFrom": date_from,
                            "dateTo": date_to,
                        },
                    },
                }

                monthly_invoices = query_all_invoices_paginated(reporter, invoice_query_params)
                monthly_summary = calculate_summary(monthly_invoices, year)

                # Update monthly fields
                update_data[f'{month_name}net'] = monthly_summary['netAmount']
                update_data[f'{month_name}invoices'] = monthly_summary['totalInvoices']

                total_invoices += monthly_summary['totalInvoices']
                total_net += monthly_summary['netAmount']

                logger.info(f"    {month_name}: {monthly_summary['totalInvoices']} invoices, {monthly_summary['netAmount']} Ft")

            except Exception as ex:
                logger.error(f"  Error querying {month_name}: {str(ex)}")
                # Set to 0 on error
                update_data[f'{month_name}net'] = 0.0
                update_data[f'{month_name}invoices'] = 0

        # Update totals
        update_data['totalnet'] = total_net
        update_data['allinvoices'] = total_invoices

        # Update current month info
        current_month = datetime.now().month
        current_month_name = HUNGARIAN_MONTHS[current_month]
        current_month_key = ENGLISH_MONTHS[current_month]
        update_data['currentMonth_name'] = current_month_name
        update_data['currentMonth_amount'] = update_data.get(f'{current_month_key}net', 0.0)

        # Update user record in Adalo
        logger.info(f"Updating user {user_id} with Online Invoice data...")
        adalo_client.update_user_online_invoice_data(user_id, update_data)
        logger.info(f"Successfully updated user {user_id}")

        return {
            'success': True,
            'message': f'Synced {total_invoices} invoices, total net: {total_net} Ft',
            'total_invoices': total_invoices,
            'total_net': total_net
        }

    except Exception as ex:
        logger.error(f"Error syncing Online Invoice for user {user_id}: {str(ex)}", exc_info=True)
        return {
            'success': False,
            'message': f'Error: {str(ex)}',
            'total_invoices': 0,
            'total_net': 0.0
        }
