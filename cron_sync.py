"""
Cron job script for daily automatic OPG sync.

This script is called by Render.com cron job daily at 02:00 UTC.
It calls the web service /api/sync/all endpoint.
"""

import os
import sys
import requests
from datetime import datetime


def main():
    """Run daily sync via web service API."""
    api_key = os.environ.get("API_KEY")
    web_service_url = os.environ.get("WEB_SERVICE_URL", "https://opg-sync-api.onrender.com")

    if not api_key:
        print("ERROR: API_KEY environment variable not set")
        sys.exit(1)

    endpoint = f"{web_service_url}/api/sync/all"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    print(f"[{datetime.now().isoformat()}] Starting daily OPG sync...")
    print(f"Calling: {endpoint}")

    try:
        response = requests.post(endpoint, headers=headers, json={}, timeout=300)

        if response.status_code == 200:
            data = response.json()
            print(f"✓ Sync successful!")
            print(f"  Total users: {data.get('total_users', 0)}")
            print(f"  Successful: {data.get('successful', 0)}")
            print(f"  Failed: {data.get('failed', 0)}")
            sys.exit(0)
        else:
            print(f"✗ Sync failed with status {response.status_code}")
            print(f"  Response: {response.text}")
            sys.exit(1)

    except requests.RequestException as e:
        print(f"✗ Request failed: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
