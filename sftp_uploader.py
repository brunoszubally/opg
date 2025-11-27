"""
SFTP Uploader Module

Handles uploading XML files to SFTP server with directory structure:
/ap_number/year/ (e.g., /A29200455/2025/)
"""

import os
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
import paramiko


class SFTPUploader:
    """SFTP uploader for NAV OPG XML files."""

    def __init__(self, host: str, username: str, password: str, port: int = 22, base_path: str = "/"):
        """
        Initialize SFTP uploader.

        Args:
            host: SFTP server hostname
            username: SFTP username
            password: SFTP password
            port: SFTP port (default 22)
            base_path: Base directory on server (default "/")
        """
        self.host = host
        self.username = username
        self.password = password
        self.port = port
        self.base_path = base_path.rstrip('/')
        self.client = None
        self.sftp = None

    def connect(self) -> bool:
        """
        Connect to SFTP server.

        Returns:
            True if connected successfully, False otherwise
        """
        try:
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            self.client.connect(
                hostname=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                timeout=30
            )

            self.sftp = self.client.open_sftp()
            return True

        except Exception as e:
            print(f"SFTP connection failed: {e}")
            return False

    def disconnect(self):
        """Disconnect from SFTP server."""
        if self.sftp:
            self.sftp.close()
        if self.client:
            self.client.close()

    def _ensure_directory(self, remote_path: str) -> bool:
        """
        Ensure directory exists on SFTP server, create if needed.

        Args:
            remote_path: Remote directory path

        Returns:
            True if directory exists or was created, False otherwise
        """
        try:
            self.sftp.stat(remote_path)
            return True
        except FileNotFoundError:
            # Directory doesn't exist, try to create it
            try:
                # Create parent directories recursively
                parent = str(Path(remote_path).parent)
                if parent != '/' and parent != remote_path:
                    self._ensure_directory(parent)

                self.sftp.mkdir(remote_path)
                print(f"  Created directory: {remote_path}")
                return True
            except Exception as e:
                print(f"  Failed to create directory {remote_path}: {e}")
                return False

    def upload_file(self, local_path: Path, remote_path: str) -> bool:
        """
        Upload single file to SFTP server.

        Args:
            local_path: Local file path
            remote_path: Remote file path

        Returns:
            True if uploaded successfully, False otherwise
        """
        try:
            # Ensure directory exists
            remote_dir = str(Path(remote_path).parent)
            if not self._ensure_directory(remote_dir):
                return False

            # Upload file
            self.sftp.put(str(local_path), remote_path)
            print(f"  Uploaded: {local_path.name} -> {remote_path}")
            return True

        except Exception as e:
            print(f"  Failed to upload {local_path.name}: {e}")
            return False

    def upload_xml_files(self, xml_files: List[Path], ap_number: str, year: int) -> Dict:
        """
        Upload multiple XML files to SFTP server.

        Directory structure: /base_path/ap_number/year/
        Example: /A29200455/2025/A29200455_69785346_20251119174852_1079.xml

        Args:
            xml_files: List of XML file paths to upload
            ap_number: AP number (e.g., A29200455)
            year: Year (e.g., 2025)

        Returns:
            Dict with upload results: {
                'success': bool,
                'uploaded': int,
                'failed': int,
                'files': List[str]
            }
        """
        result = {
            'success': False,
            'uploaded': 0,
            'failed': 0,
            'files': []
        }

        if not xml_files:
            result['success'] = True
            return result

        # Connect to SFTP
        if not self.connect():
            return result

        try:
            # Create remote directory path: /base_path/ap_number/year/
            remote_dir = f"{self.base_path}/{ap_number}/{year}"

            print(f"  Uploading {len(xml_files)} XML files to {remote_dir}...")

            # Upload each file
            for xml_file in xml_files:
                remote_path = f"{remote_dir}/{xml_file.name}"

                if self.upload_file(xml_file, remote_path):
                    result['uploaded'] += 1
                    result['files'].append(xml_file.name)
                else:
                    result['failed'] += 1

            result['success'] = result['failed'] == 0

        finally:
            self.disconnect()

        return result


def upload_files_to_sftp(xml_files: List[Path], ap_number: str, year: int,
                        sftp_host: str, sftp_user: str, sftp_password: str,
                        sftp_port: int = 22, sftp_base_path: str = "/") -> Dict:
    """
    Upload XML files to SFTP server.

    Convenience function that creates uploader, uploads files, and returns results.

    Args:
        xml_files: List of XML file paths
        ap_number: AP number (e.g., A29200455)
        year: Year (e.g., 2025)
        sftp_host: SFTP server hostname
        sftp_user: SFTP username
        sftp_password: SFTP password
        sftp_port: SFTP port (default 22)
        sftp_base_path: Base directory on server (default "/")

    Returns:
        Dict with upload results
    """
    uploader = SFTPUploader(
        host=sftp_host,
        username=sftp_user,
        password=sftp_password,
        port=sftp_port,
        base_path=sftp_base_path
    )

    return uploader.upload_xml_files(xml_files, ap_number, year)


if __name__ == "__main__":
    # Test SFTP uploader
    import sys

    if len(sys.argv) < 2:
        print("Usage: python3 sftp_uploader.py <xml_file_path>")
        sys.exit(1)

    test_file = Path(sys.argv[1])
    if not test_file.exists():
        print(f"File not found: {test_file}")
        sys.exit(1)

    # Get SFTP config from environment
    sftp_host = os.getenv('SFTP_HOST')
    sftp_user = os.getenv('SFTP_USER')
    sftp_password = os.getenv('SFTP_PASSWORD')
    sftp_port = int(os.getenv('SFTP_PORT', '22'))

    if not all([sftp_host, sftp_user, sftp_password]):
        print("Missing SFTP configuration in environment variables")
        print("Required: SFTP_HOST, SFTP_USER, SFTP_PASSWORD")
        sys.exit(1)

    # Test upload
    result = upload_files_to_sftp(
        xml_files=[test_file],
        ap_number="A29200455",
        year=2025,
        sftp_host=sftp_host,
        sftp_user=sftp_user,
        sftp_password=sftp_password,
        sftp_port=sftp_port
    )

    print(f"\nUpload result: {result}")
