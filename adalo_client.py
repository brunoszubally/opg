"""
Adalo API Client

Wrapper for Adalo REST API to manage users and daily revenue records.
"""

import os
import time
from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta, timezone
import requests


class AdaloClient:
    """Client for interacting with Adalo Collections API."""

    BASE_URL = "https://api.adalo.com/v0/apps"
    RATE_LIMIT_DELAY = 0.2  # 5 req/sec = 0.2s between requests

    def __init__(self, app_id: str, api_key: str, users_collection_id: str, revenues_collection_id: str):
        """
        Initialize Adalo API client.

        Args:
            app_id: Adalo app ID
            api_key: Adalo API Bearer token
            users_collection_id: Users collection ID (e.g., t_13c9aa8bd9dd423b8118565dec7fb3de)
            revenues_collection_id: Daily revenues collection ID (e.g., t_22imanannzgjm04zm2rbifxzm)
        """
        self.app_id = app_id
        self.api_key = api_key
        self.users_collection_id = users_collection_id
        self.revenues_collection_id = revenues_collection_id
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        self.last_request_time = 0

    def _rate_limit(self):
        """Enforce rate limiting (5 req/sec)."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.RATE_LIMIT_DELAY:
            time.sleep(self.RATE_LIMIT_DELAY - elapsed)
        self.last_request_time = time.time()

    def _get_collection_url(self, collection_id: str) -> str:
        """Get full URL for a collection."""
        return f"{self.BASE_URL}/{self.app_id}/collections/{collection_id}"

    def _request(self, method: str, url: str, **kwargs) -> Dict[str, Any]:
        """
        Make HTTP request with rate limiting and error handling.

        Args:
            method: HTTP method (GET, POST, PUT, etc.)
            url: Request URL
            **kwargs: Additional arguments for requests

        Returns:
            Response JSON

        Raises:
            Exception: If request fails
        """
        self._rate_limit()

        response = requests.request(method, url, headers=self.headers, **kwargs)

        if response.status_code == 429:
            # Rate limited, wait and retry once
            time.sleep(1)
            self._rate_limit()
            response = requests.request(method, url, headers=self.headers, **kwargs)

        if response.status_code >= 400:
            raise Exception(f"Adalo API error {response.status_code}: {response.text}")

        return response.json()

    def get_all_users(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get all users with pagination.

        Args:
            limit: Records per page (max 100)

        Returns:
            List of user records
        """
        url = self._get_collection_url(self.users_collection_id)
        offset = 0
        all_users = []

        while True:
            params = {"offset": offset, "limit": limit}
            data = self._request("GET", url, params=params)

            records = data.get("records", [])
            if not records:
                break

            all_users.extend(records)
            offset += len(records)

            # If we got fewer records than limit, we're done
            if len(records) < limit:
                break

        return all_users

    def get_users_to_sync(self, days_threshold: int = 10) -> List[Dict[str, Any]]:
        """
        Get users that need syncing (10+ days since last sync or never synced).

        Args:
            days_threshold: Number of days since last sync to trigger re-sync

        Returns:
            List of users that need syncing
        """
        all_users = self.get_all_users()
        threshold_date = datetime.now(timezone.utc) - timedelta(days=days_threshold)
        users_to_sync = []

        for user in all_users:
            # Check if OPG is enabled for this user
            if not user.get("onlinepenztargep"):
                continue

            # Check if user has NAV credentials
            if not all([
                user.get("navlogin"),
                user.get("navpassword"),
                user.get("signKey"),
                user.get("taxNumber"),
                user.get("apnumber")
            ]):
                continue

            # Check last sync date
            last_sync = user.get("lastbizonylatszinkron")
            if last_sync is None:
                # Never synced
                users_to_sync.append(user)
            else:
                # Parse ISO date string
                try:
                    last_sync_dt = datetime.fromisoformat(last_sync.replace('Z', '+00:00'))

                    # Skip if already synced today
                    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
                    if last_sync_dt >= today:
                        # Already synced today, skip
                        continue

                    if last_sync_dt < threshold_date:
                        users_to_sync.append(user)
                except (ValueError, AttributeError):
                    # Invalid date, sync anyway
                    users_to_sync.append(user)

        return users_to_sync

    def create_daily_revenue(self, user_id: int, user_adoszama: str, date: str,
                           file_number: int, receipts_count: int, total_revenue: int) -> Dict[str, Any]:
        """
        Create a new daily revenue record.

        Args:
            user_id: User ID (for relationship)
            user_adoszama: User tax number
            date: Date string (YYYY-MM-DD)
            file_number: File number from NAV
            receipts_count: Number of receipts
            total_revenue: Total revenue in HUF (forint)

        Returns:
            Created record
        """
        url = self._get_collection_url(self.revenues_collection_id)

        payload = {
            "user_adoszama": user_adoszama,
            "user_opginvoice": user_id,  # Relationship to users collection
            "fajl_sorszama": str(file_number),
            "volt_tranzakcio": str(receipts_count),
            "bizonylatsummary": str(total_revenue),
            "fajldatuma": date  # ISO date format: YYYY-MM-DD
        }

        return self._request("POST", url, json=payload)

    def update_user_sync(self, user_id: int, last_sync_at: str, last_file_number: int) -> Dict[str, Any]:
        """
        Update user's last sync timestamp and file number.

        Args:
            user_id: User ID
            last_sync_at: Last sync timestamp (ISO format)
            last_file_number: Last synced file number

        Returns:
            Updated user record
        """
        url = f"{self._get_collection_url(self.users_collection_id)}/{user_id}"

        payload = {
            "lastbizonylatszinkron": last_sync_at,
            "lastbizonylatletoltve": str(last_file_number)
        }

        return self._request("PUT", url, json=payload)

    def get_user_by_id(self, user_id: int) -> Dict[str, Any]:
        """
        Get a single user by ID.

        Args:
            user_id: User ID

        Returns:
            User record
        """
        url = f"{self._get_collection_url(self.users_collection_id)}/{user_id}"
        return self._request("GET", url)

    def update_user_online_invoice_data(self, user_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update user's Online Invoice monthly aggregation data

        Args:
            user_id: User ID
            data: Dict with monthly fields (jannet, febrinvoices, etc.) and totals

        Returns:
            Updated user record
        """
        url = f"{self._get_collection_url(self.users_collection_id)}/{user_id}"
        return self._request("PUT", url, json=data)


def create_client_from_env() -> AdaloClient:
    """
    Create AdaloClient instance from environment variables.

    Required env vars:
        - ADALO_APP_ID
        - ADALO_API_KEY
        - ADALO_USERS_COLLECTION_ID
        - ADALO_REVENUES_COLLECTION_ID

    Returns:
        Configured AdaloClient instance
    """
    return AdaloClient(
        app_id=os.environ["ADALO_APP_ID"],
        api_key=os.environ["ADALO_API_KEY"],
        users_collection_id=os.environ["ADALO_USERS_COLLECTION_ID"],
        revenues_collection_id=os.environ["ADALO_REVENUES_COLLECTION_ID"]
    )


if __name__ == "__main__":
    # Test the client
    client = create_client_from_env()

    print("Testing Adalo API client...")
    print(f"Fetching all users...")
    users = client.get_all_users()
    print(f"Found {len(users)} users")

    print(f"\nUsers that need syncing (10+ days):")
    users_to_sync = client.get_users_to_sync(days_threshold=10)
    for user in users_to_sync:
        print(f"  - {user.get('first_name')} ({user.get('Email')}) - AP: {user.get('apnumber')}")
