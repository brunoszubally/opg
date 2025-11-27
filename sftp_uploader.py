"""
FTP Uploader Module

Handles uploading XML files to FTP server with directory structure:
/ap_number/year/ (e.g., /A29200455/2025/)
"""

import os
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
from ftplib import FTP


class FTPUploader:
    """FTP uploader for NAV OPG XML files."""

    def __init__(self, host: str, username: str, password: str, port: int = 21, base_path: str = "/"):
        """
        Initialize FTP uploader.

        Args:
            host: FTP server hostname
            username: FTP username
            password: FTP password
            port: FTP port (default 21)
            base_path: Base directory on server (default "/")
        """
        self.host = host
        self.username = username
        self.password = password
        self.port = port
        self.base_path = base_path.rstrip('/')
        self.ftp = None

    def connect(self) -> bool:
        """
        Connect to FTP server.

        Returns:
            True if connected successfully, False otherwise
        """
        try:
            self.ftp = FTP()
            self.ftp.connect(self.host, self.port, timeout=30)
            self.ftp.login(self.username, self.password)
            return True

        except Exception as e:
            print(f"FTP connection failed: {e}")
            return False

    def disconnect(self):
        """Disconnect from FTP server."""
        if self.ftp:
            try:
                self.ftp.quit()
            except:
                self.ftp.close()

    def _ensure_directory(self, remote_path: str) -> bool:
        """
        Ensure directory exists on FTP server, create if needed.

        Args:
            remote_path: Remote directory path

        Returns:
            True if directory exists or was created, False otherwise
        """
        try:
            # Try to change to directory
            self.ftp.cwd(remote_path)
            return True
        except:
            # Directory doesn't exist, try to create it
            try:
                # Create parent directories recursively
                parent = str(Path(remote_path).parent)
                if parent != '/' and parent != remote_path:
                    self._ensure_directory(parent)
                    self.ftp.cwd(parent)

                # Create directory
                dir_name = Path(remote_path).name
                self.ftp.mkd(dir_name)
                print(f"  Created directory: {remote_path}")
                return True
            except Exception as e:
                print(f"  Failed to create directory {remote_path}: {e}")
                return False

    def upload_file(self, local_path: Path, remote_path: str) -> bool:
        """
        Upload single file to FTP server.

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

            # Change to target directory
            self.ftp.cwd(remote_dir)

            # Upload file in binary mode
            with open(local_path, 'rb') as f:
                remote_filename = Path(remote_path).name
                self.ftp.storbinary(f'STOR {remote_filename}', f)

            print(f"  Uploaded: {local_path.name} -> {remote_path}")
            return True

        except Exception as e:
            print(f"  Failed to upload {local_path.name}: {e}")
            return False

    def upload_xml_files(self, xml_files: List[Path], ap_number: str, year: int) -> Dict:
        """
        Upload multiple XML files to FTP server.

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

        # Connect to FTP
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


def upload_files_to_ftp(xml_files: List[Path], ap_number: str, year: int,
                        ftp_host: str, ftp_user: str, ftp_password: str,
                        ftp_port: int = 21, ftp_base_path: str = "/") -> Dict:
    """
    Upload XML files to FTP server.

    Convenience function that creates uploader, uploads files, and returns results.

    Args:
        xml_files: List of XML file paths
        ap_number: AP number (e.g., A29200455)
        year: Year (e.g., 2025)
        ftp_host: FTP server hostname
        ftp_user: FTP username
        ftp_password: FTP password
        ftp_port: FTP port (default 21)
        ftp_base_path: Base directory on server (default "/")

    Returns:
        Dict with upload results
    """
    uploader = FTPUploader(
        host=ftp_host,
        username=ftp_user,
        password=ftp_password,
        port=ftp_port,
        base_path=ftp_base_path
    )

    return uploader.upload_xml_files(xml_files, ap_number, year)


if __name__ == "__main__":
    # Test FTP uploader
    import sys

    if len(sys.argv) < 2:
        print("Usage: python3 sftp_uploader.py <xml_file_path>")
        sys.exit(1)

    test_file = Path(sys.argv[1])
    if not test_file.exists():
        print(f"File not found: {test_file}")
        sys.exit(1)

    # Get FTP config from environment
    ftp_host = os.getenv('FTP_HOST')
    ftp_user = os.getenv('FTP_USER')
    ftp_password = os.getenv('FTP_PASSWORD')
    ftp_port = int(os.getenv('FTP_PORT', '21'))

    if not all([ftp_host, ftp_user, ftp_password]):
        print("Missing FTP configuration in environment variables")
        print("Required: FTP_HOST, FTP_USER, FTP_PASSWORD")
        sys.exit(1)

    # Test upload
    result = upload_files_to_ftp(
        xml_files=[test_file],
        ap_number="A29200455",
        year=2025,
        ftp_host=ftp_host,
        ftp_user=ftp_user,
        ftp_password=ftp_password,
        ftp_port=ftp_port
    )

    print(f"\nUpload result: {result}")
