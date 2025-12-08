"""
Online Invoice API - Flask endpoint

This module provides a Flask API endpoint that mimics the functionality
of the PHP api.php file from the osz/examples directory.

Supports three modes:
1. Normal: Return all invoices
2. Summary: Monthly aggregation
3. Yearly: 12-month aggregation
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from flask import request, jsonify

from nav_online_invoice import (
    NavOnlineInvoiceConfig,
    NavOnlineInvoiceReporter,
    normalize_tax_number
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Valid API keys (same as PHP version)
VALID_API_KEYS = {
    'aXJ2b2x0YXNlY3VyZWFwaWtleTIwMjQ=': {
        'name': 'Default Client',
        'rate_limit': 100
    }
}


# Hungarian month names
HUNGARIAN_MONTHS = {
    1: 'Január', 2: 'Február', 3: 'Március', 4: 'Április',
    5: 'Május', 6: 'Június', 7: 'Július', 8: 'Augusztus',
    9: 'Szeptember', 10: 'Október', 11: 'November', 12: 'December'
}

# English month names for keys
ENGLISH_MONTHS = {
    1: 'january', 2: 'february', 3: 'march', 4: 'april',
    5: 'may', 6: 'june', 7: 'july', 8: 'august',
    9: 'september', 10: 'october', 11: 'november', 12: 'december'
}


def mask_sensitive_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Mask sensitive data (password) in dict for logging"""
    masked = data.copy()
    if 'password' in masked:
        masked['password'] = '***MASKED***'
    return masked


def validate_api_key() -> Optional[Dict[str, str]]:
    """
    Validate API key from header or query parameter

    Returns:
        API key info dict if valid, None otherwise
    """
    # Check header first
    api_key = request.headers.get('X-API-Key')

    # Fall back to query parameter
    if not api_key:
        api_key = request.args.get('apiKey')

    if not api_key or api_key not in VALID_API_KEYS:
        return None

    return VALID_API_KEYS[api_key]


def query_all_invoices_paginated(
    reporter: NavOnlineInvoiceReporter,
    invoice_query_params: Dict[str, Any],
    max_pages: int = 100
) -> List[Dict[str, Any]]:
    """
    Query all invoices with pagination

    Args:
        reporter: NAV reporter instance
        invoice_query_params: Query parameters
        max_pages: Maximum pages to fetch

    Returns:
        List of all invoice dicts
    """
    page = 1
    all_invoices = []

    while page <= max_pages:
        logger.info(f"Querying page {page}...")

        result = reporter.query_invoice_digest(invoice_query_params, page, "OUTBOUND")

        invoices = result.get('invoiceDigest', [])
        if invoices:
            logger.info(f"Found {len(invoices)} invoices on page {page}")
            all_invoices.extend(invoices)

        available_pages = result.get('availablePage', 1)
        logger.info(f"Available pages: {available_pages}")

        if page >= available_pages:
            break

        page += 1

    logger.info(f"Total invoices fetched: {len(all_invoices)}")
    return all_invoices


def calculate_summary(invoices: List[Dict[str, Any]], current_year: int) -> Dict[str, Any]:
    """
    Calculate summary statistics from invoices

    Args:
        invoices: List of invoice dicts
        current_year: Current year for cross-year detection

    Returns:
        Summary dict with totals
    """
    total_amount = 0.0
    storno_amount = 0.0
    modified_amount = 0.0
    valid_invoices = 0
    storno_invoices = 0
    modified_invoices = 0
    cross_year_stornos = 0
    cross_year_modified = 0

    for invoice in invoices:
        amount = float(invoice.get('invoiceNetAmountHUF', 0))
        operation = invoice.get('invoiceOperation', 'CREATE')

        # Check if cross-year (delivery date in previous year)
        is_cross_year = False
        if operation in ['STORNO', 'MODIFY']:
            delivery_date = invoice.get('invoiceDeliveryDate')
            if delivery_date:
                try:
                    delivery_year = int(delivery_date[:4])
                    if delivery_year < current_year:
                        is_cross_year = True
                except:
                    pass

        if not is_cross_year:
            if operation == 'STORNO':
                storno_amount += abs(amount)
                storno_invoices += 1
            elif operation == 'MODIFY':
                modified_amount += amount
                modified_invoices += 1
            elif operation == 'CREATE':
                total_amount += amount
                valid_invoices += 1
        else:
            # Count cross-year operations
            if operation == 'STORNO':
                cross_year_stornos += 1
                storno_invoices += 1
            elif operation == 'MODIFY':
                cross_year_modified += 1
                modified_invoices += 1

    return {
        'totalAmount': total_amount,
        'stornoAmount': storno_amount,
        'modifiedAmount': modified_amount,
        'netAmount': total_amount + modified_amount - storno_amount,
        'validInvoices': valid_invoices,
        'stornoInvoices': storno_invoices,
        'modifiedInvoices': modified_invoices,
        'totalInvoices': len(invoices),
        'crossYearStornos': cross_year_stornos,
        'crossYearModified': cross_year_modified
    }


def handle_online_invoice_query():
    """
    Main handler for online invoice queries

    Mimics the behavior of osz/examples/api.php
    """
    try:
        logger.info("=== ONLINE INVOICE QUERY REQUEST STARTED ===")
        logger.info(f"Request method: {request.method}")

        # Validate API key
        api_key_info = validate_api_key()
        if not api_key_info:
            logger.warning("Invalid API key")
            return jsonify({'error': 'Érvénytelen API kulcs'}), 401

        logger.info(f"API key valid: {api_key_info['name']}")

        # Get request data (POST JSON or GET params)
        if request.method == 'POST':
            request_data = request.get_json(silent=True) or {}
            logger.info(f"POST data (safe): {mask_sensitive_data(request_data)}")
        else:
            request_data = request.args.to_dict()
            logger.info(f"GET params (safe): {mask_sensitive_data(request_data)}")

        # Normalize tax number
        if 'taxNumber' in request_data:
            normalized_tax = normalize_tax_number(request_data['taxNumber'])
            if not normalized_tax:
                logger.error(f"Invalid taxNumber: {request_data['taxNumber']}")
                return jsonify({
                    'error': 'Érvénytelen adószám formátum. Legalább 8 egymást követő számjegyet várunk a taxNumber-ben.'
                }), 400
            request_data['taxNumber'] = normalized_tax
            logger.info(f"Normalized taxNumber to: {normalized_tax}")

        # Check required parameters
        required_params = ['login', 'password', 'taxNumber', 'signKey', 'exchangeKey', 'dateFrom', 'dateTo']
        missing_params = [p for p in required_params if p not in request_data or request_data[p] == '']

        if missing_params:
            logger.error(f"Missing parameters: {missing_params}")
            return jsonify({
                'error': 'Hiányzó paraméterek',
                'missing': missing_params
            }), 400

        # Build user data
        user_data = {
            "login": request_data['login'],
            "password": request_data['password'],
            "taxNumber": request_data['taxNumber'],
            "signKey": request_data['signKey'],
            "exchangeKey": request_data['exchangeKey']
        }

        # Build software data (fixed values)
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
        logger.info("Creating NAV Online Invoice client...")
        config = NavOnlineInvoiceConfig(NavOnlineInvoiceConfig.PROD_URL, user_data, software_data)
        reporter = NavOnlineInvoiceReporter(config)
        logger.info("NAV client created successfully")

        # Check if yearly summary is requested
        if request_data.get('yearly') == 'true':
            logger.info("Yearly summary requested")
            return handle_yearly_summary(reporter, request_data)

        # Normal or monthly summary query
        invoice_query_params = {
            "mandatoryQueryParams": {
                "invoiceIssueDate": {
                    "dateFrom": request_data['dateFrom'],
                    "dateTo": request_data['dateTo'],
                },
            },
        }

        # Fetch all invoices with pagination
        logger.info(f"Fetching invoices from {request_data['dateFrom']} to {request_data['dateTo']}")
        all_invoices = query_all_invoices_paginated(reporter, invoice_query_params)

        # Check if summary is requested
        if request_data.get('summary') == 'true':
            logger.info("Summary mode requested")

            # Determine current year/month from dateFrom
            current_year = int(datetime.fromisoformat(request_data['dateFrom']).year)
            current_month = int(datetime.fromisoformat(request_data['dateFrom']).month)
            current_month_name = HUNGARIAN_MONTHS[current_month]

            summary = calculate_summary(all_invoices, current_year)
            summary['currentMonth'] = {
                'name': current_month_name,
                'netAmount': summary['netAmount']
            }

            response = {
                'success': True,
                'summary': summary,
                'cached': False
            }
        else:
            # Normal mode - return all invoices
            logger.info("Normal mode - returning all invoices")
            response = {
                'success': True,
                'count': len(all_invoices),
                'invoices': all_invoices,
                'cached': False
            }

        logger.info("Request completed successfully")
        return jsonify(response), 200

    except Exception as ex:
        logger.error(f"Error processing request: {str(ex)}", exc_info=True)
        return jsonify({
            'error': str(ex),
            'type': type(ex).__name__
        }), 500


def handle_yearly_summary(reporter: NavOnlineInvoiceReporter, request_data: Dict[str, Any]) -> tuple:
    """
    Handle yearly summary request (all 12 months)

    Args:
        reporter: NAV reporter instance
        request_data: Request parameters

    Returns:
        Tuple of (response dict, status code)
    """
    year = datetime.fromisoformat(request_data['dateFrom']).year

    yearly_summary = {
        'totalAmount': 0.0,
        'stornoAmount': 0.0,
        'modifiedAmount': 0.0,
        'netAmount': 0.0,
        'validInvoices': 0,
        'stornoInvoices': 0,
        'modifiedInvoices': 0,
        'totalInvoices': 0,
        'crossYearStornos': 0,
        'crossYearModified': 0
    }

    # Query each month
    for month in range(1, 13):
        date_from = f"{year}-{month:02d}-01"
        # Get last day of month
        if month == 12:
            date_to = f"{year}-12-31"
        else:
            next_month = datetime(year, month + 1, 1)
            last_day = (next_month - timedelta(days=1)).day
            date_to = f"{year}-{month:02d}-{last_day:02d}"

        month_name = ENGLISH_MONTHS[month]
        logger.info(f"Querying month {month} ({month_name}) from {date_from} to {date_to}")

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
            logger.info(f"Finished querying month {month}. Total invoices: {len(monthly_invoices)}")

            # Calculate monthly summary
            monthly_summary = calculate_summary(monthly_invoices, year)

            # Add to yearly summary
            yearly_summary[f'{month_name}TotalAmount'] = monthly_summary['totalAmount']
            yearly_summary[f'{month_name}StornoAmount'] = monthly_summary['stornoAmount']
            yearly_summary[f'{month_name}ModifiedAmount'] = monthly_summary['modifiedAmount']
            yearly_summary[f'{month_name}NetAmount'] = monthly_summary['netAmount']
            yearly_summary[f'{month_name}ValidInvoices'] = monthly_summary['validInvoices']
            yearly_summary[f'{month_name}StornoInvoices'] = monthly_summary['stornoInvoices']
            yearly_summary[f'{month_name}ModifiedInvoices'] = monthly_summary['modifiedInvoices']
            yearly_summary[f'{month_name}TotalInvoices'] = monthly_summary['totalInvoices']

            # Update yearly totals
            yearly_summary['totalAmount'] += monthly_summary['totalAmount']
            yearly_summary['stornoAmount'] += monthly_summary['stornoAmount']
            yearly_summary['modifiedAmount'] += monthly_summary['modifiedAmount']
            yearly_summary['netAmount'] += monthly_summary['netAmount']
            yearly_summary['validInvoices'] += monthly_summary['validInvoices']
            yearly_summary['stornoInvoices'] += monthly_summary['stornoInvoices']
            yearly_summary['modifiedInvoices'] += monthly_summary['modifiedInvoices']
            yearly_summary['totalInvoices'] += monthly_summary['totalInvoices']
            yearly_summary['crossYearStornos'] += monthly_summary['crossYearStornos']
            yearly_summary['crossYearModified'] += monthly_summary['crossYearModified']

        except Exception as ex:
            error_msg = f'Error querying month {month}: {str(ex)}'
            logger.error(error_msg)
            yearly_summary[f'{month_name}Error'] = error_msg

    # Current month info
    current_month = datetime.now().month
    current_month_name = HUNGARIAN_MONTHS[current_month]
    current_month_key = ENGLISH_MONTHS[current_month]

    response = {
        'success': True,
        'yearlySummary': yearly_summary,
        'currentMonth': {
            'name': current_month_name,
            'netAmount': yearly_summary.get(f'{current_month_key}NetAmount', 0)
        },
        'cached': False
    }

    logger.info(f"Finished yearly processing. Total invoices: {yearly_summary['totalInvoices']}")
    return jsonify(response), 200
