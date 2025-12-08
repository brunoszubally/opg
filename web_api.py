import os
import logging
import traceback
from datetime import datetime
from flask import Flask, jsonify, request
from functools import wraps

from adalo_client import create_client_from_env
from sync_service import sync_all_users, sync_user
from online_invoice_api import handle_online_invoice_query


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# API Key for authentication
API_KEY = os.environ.get("API_KEY", "")


def require_api_key(f):
    """Decorator to require API key authentication."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check Authorization header
        auth_header = request.headers.get('Authorization')

        if not auth_header:
            return jsonify({'error': 'Missing Authorization header'}), 401

        # Expected format: "Bearer {api_key}"
        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != 'bearer':
            return jsonify({'error': 'Invalid Authorization header format'}), 401

        provided_key = parts[1]

        if provided_key != API_KEY:
            return jsonify({'error': 'Invalid API key'}), 403

        return f(*args, **kwargs)

    return decorated_function


@app.route('/health', methods=['GET'])
def health_check():
    """
    Health check endpoint.

    Returns:
        200 OK with status info
    """
    return jsonify({
        'status': 'healthy',
        'service': 'opg-sync-service',
        'timestamp': datetime.now().isoformat()
    }), 200


@app.route('/api/sync/all', methods=['POST'])
@require_api_key
def sync_all():
    """
    Sync all users that need syncing (10+ days since last sync).

    This endpoint is called by the daily cron job.

    Headers:
        Authorization: Bearer {api_key}

    Request body (optional JSON):
        {
            "days_threshold": 10,  # Optional, defaults to 10
            "current_year": 2025    # Optional, defaults to current year
        }

    Returns:
        200 OK with sync results
        500 Error if sync fails
    """
    try:
        logger.info("=== SYNC ALL REQUEST STARTED ===")

        # Parse request body (silent=True to handle empty body)
        data = request.get_json(silent=True) or {}
        days_threshold = data.get('days_threshold', 10)
        current_year = data.get('current_year', datetime.now().year)

        logger.info(f"Request params: days_threshold={days_threshold}, current_year={current_year}")

        # Create Adalo client
        logger.info("Creating Adalo client from environment...")
        adalo_client = create_client_from_env()
        logger.info("Adalo client created successfully")

        # Run sync
        logger.info("Starting sync_all_users...")
        results = sync_all_users(adalo_client, days_threshold=days_threshold, current_year=current_year)
        logger.info(f"Sync completed successfully: {results}")

        return jsonify({
            'success': True,
            'timestamp': datetime.now().isoformat(),
            **results
        }), 200

    except Exception as e:
        logger.error(f"=== SYNC ALL ERROR ===")
        logger.error(f"Error: {str(e)}")
        logger.error(f"Traceback:\n{traceback.format_exc()}")

        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500


@app.route('/api/sync/<int:user_id>', methods=['POST'])
@require_api_key
def sync_single_user(user_id: int):
    """
    Manually sync a specific user.

    This endpoint is called when a user triggers manual sync.

    Headers:
        Authorization: Bearer {api_key}

    URL Parameters:
        user_id: User ID in Adalo database

    Request body (optional JSON):
        {
            "current_year": 2025  # Optional, defaults to current year
        }

    Returns:
        200 OK with sync result
        404 Not Found if user doesn't exist
        500 Error if sync fails
    """
    try:
        logger.info(f"=== SYNC USER {user_id} REQUEST STARTED ===")

        # Parse request body (silent=True to handle empty body)
        data = request.get_json(silent=True) or {}
        current_year = data.get('current_year', datetime.now().year)

        logger.info(f"Request params: user_id={user_id}, current_year={current_year}")

        # Create Adalo client
        logger.info("Creating Adalo client from environment...")
        adalo_client = create_client_from_env()
        logger.info("Adalo client created successfully")

        # Get user
        try:
            logger.info(f"Fetching user {user_id} from Adalo...")
            user = adalo_client.get_user_by_id(user_id)
            logger.info(f"User fetched: {user.get('first_name')} ({user.get('Email')})")
            logger.info(f"User credentials present: navlogin={bool(user.get('navlogin'))}, navpassword={bool(user.get('navpassword'))}, signKey={bool(user.get('signKey'))}, taxNumber={bool(user.get('taxNumber'))}, apnumber={user.get('apnumber')}")
        except Exception as e:
            logger.error(f"Failed to fetch user {user_id}: {str(e)}")
            logger.error(f"Traceback:\n{traceback.format_exc()}")
            return jsonify({
                'success': False,
                'error': f'User not found: {str(e)}',
                'timestamp': datetime.now().isoformat()
            }), 404

        # Run sync
        logger.info(f"Starting sync for user {user_id}...")
        result = sync_user(user, adalo_client, current_year=current_year)
        logger.info(f"Sync result: {result}")

        status_code = 200 if result['success'] else 500

        return jsonify({
            'timestamp': datetime.now().isoformat(),
            'user_id': user_id,
            'user_name': user.get('first_name'),
            'user_email': user.get('Email'),
            **result
        }), status_code

    except Exception as e:
        logger.error(f"=== SYNC USER {user_id} ERROR ===")
        logger.error(f"Error: {str(e)}")
        logger.error(f"Traceback:\n{traceback.format_exc()}")

        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500


@app.route('/api/status', methods=['GET'])
@require_api_key
def get_status():
    """
    Get sync status for all users.

    Headers:
        Authorization: Bearer {api_key}

    Returns:
        200 OK with user sync status
    """
    try:
        adalo_client = create_client_from_env()
        users = adalo_client.get_all_users()

        user_status = []
        for user in users:
            # Only include users with OPG credentials
            if user.get('apnumber'):
                user_status.append({
                    'user_id': user['id'],
                    'user_name': user.get('first_name'),
                    'user_email': user.get('Email'),
                    'ap_number': user.get('apnumber'),
                    'last_sync': user.get('lastbizonylatszinkron'),
                    'last_file_number': user.get('lastbizonylatletoltve')
                })

        return jsonify({
            'success': True,
            'timestamp': datetime.now().isoformat(),
            'total_users': len(user_status),
            'users': user_status
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500


@app.route('/api/online-invoice/query', methods=['GET', 'POST'])
def online_invoice_query():
    """
    Query NAV Online Invoice data

    This endpoint provides access to NAV Online Invoice (OSZ) system.
    Supports three modes:
    1. Normal: Return all invoices (invoices list)
    2. Summary: Monthly aggregation (summary object with totals)
    3. Yearly: 12-month aggregation (yearlySummary object)

    Authentication:
        X-API-Key header or apiKey query parameter

    Parameters (POST JSON or GET query):
        login (required): NAV technical user login
        password (required): NAV technical user password
        taxNumber (required): Tax number (8 digits, HU prefix optional)
        signKey (required): Signature key
        exchangeKey (required): Exchange key
        dateFrom (required): Start date (YYYY-MM-DD)
        dateTo (required): End date (YYYY-MM-DD)
        summary (optional): "true" for monthly summary
        yearly (optional): "true" for yearly summary (12 months)

    Returns:
        200 OK with invoice data
        400 Bad Request if parameters are missing or invalid
        401 Unauthorized if API key is invalid
        500 Error if NAV query fails
    """
    return handle_online_invoice_query()


@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors."""
    return jsonify({
        'error': 'Not found',
        'message': 'The requested endpoint does not exist'
    }), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors."""
    return jsonify({
        'error': 'Internal server error',
        'message': str(error)
    }), 500


if __name__ == '__main__':
    # Run in development mode
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
