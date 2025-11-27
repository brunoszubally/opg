"""
OPG Sync Service

Main sync logic for downloading NAV OPG log files, parsing XML, aggregating
daily revenues, and storing in Adalo database.
"""

import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Optional
from collections import defaultdict
import tempfile
import shutil


# Load .env file manually
def load_env():
    """Load environment variables from .env file."""
    env_path = Path(__file__).parent / '.env'
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()


load_env()

# Import NAV API functions from opg.py
import opg
from adalo_client import AdaloClient
from sftp_uploader import upload_files_to_sftp


def get_nav_status(ap_number: str, credentials: Dict) -> Optional[Dict]:
    """
    Query NAV API for cash register status using opg.py CLI.

    Args:
        ap_number: AP number (e.g., A29200455)
        credentials: Dict with navlogin, navpassword, signKey, taxNumber

    Returns:
        Dict with 'min', 'max', 'ap' or None if error
    """
    # WORKAROUND: Use opg.py CLI as subprocess since module import doesn't work
    # We need to temporarily modify opg.py with user credentials

    import subprocess

    opg_path = Path(__file__).parent / 'opg.py'
    backup_path = Path(__file__).parent / 'opg.py.backup'

    try:
        # Backup original opg.py
        opg_content = opg_path.read_text()
        backup_path.write_text(opg_content)

        # Modify opg.py with user credentials
        modified = opg_content
        modified = modified.replace(
            f'TECH_LOGIN      = "{opg.TECH_LOGIN}"',
            f'TECH_LOGIN      = "{credentials["navlogin"]}"'
        )
        modified = modified.replace(
            f'TECH_PASSWORD   = "{opg.TECH_PASSWORD}"',
            f'TECH_PASSWORD   = "{credentials["navpassword"]}"'
        )
        modified = modified.replace(
            f'SIGNING_KEY     = "{opg.SIGNING_KEY}"',
            f'SIGNING_KEY     = "{credentials["signKey"]}"'
        )
        modified = modified.replace(
            f'TAX_NUMBER_8DIG = "{opg.TAX_NUMBER_8DIG}"',
            f'TAX_NUMBER_8DIG = "{credentials["taxNumber"][:8]}"'
        )
        modified = modified.replace(
            f'AP_NUMBER       = "{opg.AP_NUMBER}"',
            f'AP_NUMBER       = "{ap_number}"'
        )

        opg_path.write_text(modified)

        # Run opg.py status command
        result = subprocess.run(
            ['python3', str(opg_path), 'status', '--ap', ap_number],
            capture_output=True, text=True, timeout=30
        )

        if result.returncode != 0:
            print(f"    opg.py error: {result.stderr}")
            return None

        # Parse output
        output = result.stdout
        if 'Elérhető fájlok:' in output:
            # Extract: "Elérhető fájlok: 1066 - 1089 (24 db)"
            match = re.search(r'Elérhető fájlok:\s*(\d+)\s*-\s*(\d+)', output)
            if match:
                return {
                    'min': int(match.group(1)),
                    'max': int(match.group(2)),
                    'ap': ap_number
                }

        print(f"    Failed to parse status output")
        return None

    except subprocess.TimeoutExpired:
        print(f"    NAV API timeout")
        return None
    except Exception as e:
        print(f"    Exception: {e}")
        return None
    finally:
        # Restore original opg.py
        if backup_path.exists():
            opg_path.write_text(backup_path.read_text())
            backup_path.unlink()


def download_nav_files(ap_number: str, start_file: int, end_file: int,
                       credentials: Dict, output_dir: Path) -> List[Path]:
    """
    Download NAV log files using opg.py CLI (workaround for module import issues).

    Args:
        ap_number: AP number
        start_file: First file number to download
        end_file: Last file number to download
        credentials: NAV credentials dict
        output_dir: Directory to save files

    Returns:
        List of extracted XML file paths
    """
    import subprocess
    import glob

    opg_path = Path(__file__).parent / 'opg.py'
    backup_path = Path(__file__).parent / 'opg.py.backup'

    try:
        # Backup and modify opg.py with user credentials
        opg_content = opg_path.read_text()
        backup_path.write_text(opg_content)

        modified = opg_content
        modified = modified.replace(
            f'TECH_LOGIN      = "{opg.TECH_LOGIN}"',
            f'TECH_LOGIN      = "{credentials["navlogin"]}"'
        )
        modified = modified.replace(
            f'TECH_PASSWORD   = "{opg.TECH_PASSWORD}"',
            f'TECH_PASSWORD   = "{credentials["navpassword"]}"'
        )
        modified = modified.replace(
            f'SIGNING_KEY     = "{opg.SIGNING_KEY}"',
            f'SIGNING_KEY     = "{credentials["signKey"]}"'
        )
        modified = modified.replace(
            f'TAX_NUMBER_8DIG = "{opg.TAX_NUMBER_8DIG}"',
            f'TAX_NUMBER_8DIG = "{credentials["taxNumber"][:8]}"'
        )

        opg_path.write_text(modified)

        # Run opg.py download-all command
        output_dir.mkdir(parents=True, exist_ok=True)

        result = subprocess.run(
            ['python3', str(opg_path), 'download-all', '--ap', ap_number, '--out', str(output_dir)],
            capture_output=True, text=True, timeout=180
        )

        if result.returncode != 0:
            raise Exception(f"opg.py download-all failed: {result.stderr}")

        # Find all extracted XML files
        xml_files = []
        for xml_path in output_dir.glob('*/A*.xml'):
            xml_files.append(xml_path)

        return xml_files

    finally:
        # Restore original opg.py
        if backup_path.exists():
            opg_path.write_text(backup_path.read_text())
            backup_path.unlink()


def parse_xml_receipts(xml_path: Path, current_year: int) -> List[Dict]:
    """
    Parse XML file and extract receipt data.

    Args:
        xml_path: Path to XML file
        current_year: Year to filter by (e.g., 2025)

    Returns:
        List of receipt dicts with: date, amount, cancelled, file_number
    """
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()

        # Extract file number from filename or LON element
        file_number = None
        filename = xml_path.stem
        match = re.search(r'_(\d+)$', filename)
        if match:
            file_number = int(match.group(1))

        # Parse namespace
        ns = {}
        if root.tag.startswith('{'):
            ns_match = re.match(r'\{(.*?)\}', root.tag)
            if ns_match:
                ns['ns'] = ns_match.group(1)

        # Find all NYN (receipt) elements
        receipts = []
        nyn_elements = root.findall('.//NYN') if not ns else root.findall('.//ns:NYN', ns)

        for nyn in nyn_elements:
            # DTS: receipt timestamp
            dts_elem = nyn.find('DTS') if not ns else nyn.find('ns:DTS', ns)
            if dts_elem is None or not dts_elem.text:
                continue

            # Parse date
            try:
                receipt_dt = datetime.fromisoformat(dts_elem.text.replace('+01:00', '+00:00').replace('+02:00', '+00:00'))
                if receipt_dt.year != current_year:
                    continue  # Skip if not current year
                date_str = receipt_dt.strftime('%Y-%m-%d')
            except ValueError:
                continue

            # SUM: total amount (gross)
            sum_elem = nyn.find('SUM') if not ns else nyn.find('ns:SUM', ns)
            if sum_elem is None or not sum_elem.text:
                continue

            try:
                amount = int(sum_elem.text)
            except ValueError:
                continue

            # CNC: cancelled flag (1 = cancelled, 0 or missing = not cancelled)
            cnc_elem = nyn.find('CNC') if not ns else nyn.find('ns:CNC', ns)
            cancelled = cnc_elem is not None and cnc_elem.text == '1'

            receipts.append({
                'date': date_str,
                'amount': amount,
                'cancelled': cancelled,
                'file_number': file_number
            })

        return receipts

    except ET.ParseError:
        return []


def aggregate_daily_revenues(xml_files: List[Path], current_year: int) -> Dict[str, Dict]:
    """
    Aggregate receipts by date from multiple XML files.
    Creates entries for ALL files, even if they have 0 receipts.

    Args:
        xml_files: List of XML file paths
        current_year: Year to filter by

    Returns:
        Dict keyed by file number with data:
        {
            'file_number': file number,
            'date': date string (from filename),
            'receipts_count': count of successful receipts (can be 0),
            'total_revenue': total amount (can be 0)
        }
    """
    # Process each file individually
    file_data = {}

    for xml_path in xml_files:
        # Extract file number and date from filename
        # Format: A29200455_69785346_20251119174852_1079.xml
        filename = xml_path.stem
        match = re.search(r'_(\d{14})_(\d+)$', filename)

        if not match:
            print(f"    Warning: Cannot parse filename: {filename}")
            continue

        timestamp_str = match.group(1)  # YYYYMMDDHHmmss
        file_number = int(match.group(2))

        # Parse date from timestamp
        try:
            file_date = datetime.strptime(timestamp_str[:8], '%Y%m%d')
            date_str = file_date.strftime('%Y-%m-%d')
        except ValueError:
            print(f"    Warning: Cannot parse date from: {timestamp_str}")
            continue

        # Initialize file data
        file_data[file_number] = {
            'file_number': file_number,
            'date': date_str,
            'receipts_count': 0,
            'total_revenue': 0
        }

        # Parse receipts from XML
        receipts = parse_xml_receipts(xml_path, current_year)

        for receipt in receipts:
            # Skip cancelled receipts
            if receipt['cancelled']:
                continue

            # Only count receipts from current year
            file_data[file_number]['receipts_count'] += 1
            file_data[file_number]['total_revenue'] += receipt['amount']

    return file_data


def sync_user(user: Dict, adalo_client: AdaloClient, current_year: int = None) -> Dict:
    """
    Sync a single user's OPG data.

    Args:
        user: User dict from Adalo
        adalo_client: AdaloClient instance
        current_year: Year to filter by (defaults to current year)

    Returns:
        Dict with sync result: {'success': bool, 'message': str, 'files_synced': int, 'revenues_created': int}
    """
    if current_year is None:
        current_year = datetime.now().year

    user_id = user['id']
    ap_number = user.get('apnumber')

    if not ap_number:
        return {'success': False, 'message': 'Missing AP number', 'files_synced': 0, 'revenues_created': 0}

    credentials = {
        'navlogin': user.get('navlogin'),
        'navpassword': user.get('navpassword'),
        'signKey': user.get('signKey'),
        'exchangeKey': user.get('exchangeKey', ''),
        'taxNumber': user.get('taxNumber')
    }

    # Check required credentials (exchangeKey is optional)
    required_creds = ['navlogin', 'navpassword', 'signKey', 'taxNumber']
    if not all(credentials.get(k) for k in required_creds):
        return {'success': False, 'message': 'Missing NAV credentials', 'files_synced': 0, 'revenues_created': 0}

    try:
        # Get NAV status
        print(f"  Querying NAV status for AP {ap_number}...")
        status = get_nav_status(ap_number, credentials)
        if not status:
            return {'success': False, 'message': 'Failed to query NAV status', 'files_synced': 0, 'revenues_created': 0}
        print(f"  NAV status: Files {status['min']} - {status['max']}")

        # Determine which files to download
        last_synced_file = user.get('lastbizonylatletoltve')
        if last_synced_file:
            try:
                start_file = int(last_synced_file) + 1
            except ValueError:
                start_file = status['min']
        else:
            start_file = status['min']

        end_file = status['max']

        if start_file > end_file:
            return {'success': True, 'message': 'No new files to sync', 'files_synced': 0, 'revenues_created': 0}

        # Download files to temp directory
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            xml_files = download_nav_files(ap_number, start_file, end_file, credentials, temp_path)

            if not xml_files:
                return {'success': True, 'message': 'No XML files extracted', 'files_synced': 0, 'revenues_created': 0}

            # Aggregate daily revenues (now returns dict by file_number)
            file_revenues = aggregate_daily_revenues(xml_files, current_year)

            # Create Adalo records - one per file
            revenues_created = 0
            for file_number, data in sorted(file_revenues.items()):
                adalo_client.create_daily_revenue(
                    user_id=user_id,
                    user_adoszama=credentials['taxNumber'],
                    date=data['date'],
                    file_number=file_number,
                    receipts_count=data['receipts_count'],
                    total_revenue=data['total_revenue']
                )
                revenues_created += 1

            # Upload XML files to SFTP (optional, only if configured)
            sftp_result = None
            sftp_host = os.getenv('SFTP_HOST')
            sftp_user = os.getenv('SFTP_USER')
            sftp_password = os.getenv('SFTP_PASSWORD')

            if all([sftp_host, sftp_user, sftp_password]):
                print(f"  Uploading {len(xml_files)} XML files to SFTP...")
                try:
                    sftp_port = int(os.getenv('SFTP_PORT', '22'))
                    sftp_base_path = os.getenv('SFTP_BASE_PATH', '/')

                    sftp_result = upload_files_to_sftp(
                        xml_files=xml_files,
                        ap_number=ap_number,
                        year=current_year,
                        sftp_host=sftp_host,
                        sftp_user=sftp_user,
                        sftp_password=sftp_password,
                        sftp_port=sftp_port,
                        sftp_base_path=sftp_base_path
                    )

                    if sftp_result['success']:
                        print(f"  SFTP upload successful: {sftp_result['uploaded']} files")
                    else:
                        print(f"  SFTP upload partial: {sftp_result['uploaded']} succeeded, {sftp_result['failed']} failed")

                except Exception as e:
                    print(f"  SFTP upload error: {e}")
                    sftp_result = {'success': False, 'uploaded': 0, 'failed': len(xml_files), 'error': str(e)}
            else:
                print(f"  SFTP upload skipped (not configured)")

            # Update user sync status
            now_iso = datetime.now(timezone.utc).isoformat()
            adalo_client.update_user_sync(
                user_id=user_id,
                last_sync_at=now_iso,
                last_file_number=end_file
            )

            files_synced = end_file - start_file + 1

            # Build result message
            message = f'Synced {files_synced} files, created {revenues_created} daily revenue records'
            if sftp_result:
                if sftp_result['success']:
                    message += f', uploaded {sftp_result["uploaded"]} files to SFTP'
                else:
                    message += f', SFTP upload partial ({sftp_result["uploaded"]}/{len(xml_files)} files)'

            return {
                'success': True,
                'message': message,
                'files_synced': files_synced,
                'revenues_created': revenues_created,
                'sftp_uploaded': sftp_result['uploaded'] if sftp_result else None
            }

    except Exception as e:
        return {'success': False, 'message': f'Error: {str(e)}', 'files_synced': 0, 'revenues_created': 0}


def sync_all_users(adalo_client: AdaloClient, days_threshold: int = 10, current_year: int = None) -> Dict:
    """
    Sync all users that need syncing (10+ days since last sync).

    Args:
        adalo_client: AdaloClient instance
        days_threshold: Number of days to trigger re-sync
        current_year: Year to filter by (defaults to current year)

    Returns:
        Dict with overall sync results
    """
    if current_year is None:
        current_year = datetime.now().year

    users_to_sync = adalo_client.get_users_to_sync(days_threshold=days_threshold)

    results = {
        'total_users': len(users_to_sync),
        'successful': 0,
        'failed': 0,
        'user_results': []
    }

    for user in users_to_sync:
        print(f"Syncing user {user['id']} - {user.get('first_name')} ({user.get('Email')})...")
        result = sync_user(user, adalo_client, current_year)

        if result['success']:
            results['successful'] += 1
        else:
            results['failed'] += 1

        results['user_results'].append({
            'user_id': user['id'],
            'user_name': user.get('first_name'),
            'user_email': user.get('Email'),
            **result
        })

    return results


if __name__ == "__main__":
    # Test sync service
    from adalo_client import create_client_from_env

    client = create_client_from_env()
    print("Starting sync for all users...")
    results = sync_all_users(client, days_threshold=10, current_year=2025)

    print(f"\n=== Sync Results ===")
    print(f"Total users: {results['total_users']}")
    print(f"Successful: {results['successful']}")
    print(f"Failed: {results['failed']}")

    print(f"\nUser details:")
    for user_result in results['user_results']:
        status = "✓" if user_result['success'] else "✗"
        print(f"  {status} {user_result['user_name']} - {user_result['message']}")
