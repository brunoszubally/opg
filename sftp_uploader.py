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

    def __init__(self, host: str, username: str, password: str, port: int = 21, base_path: str = "users/opg_bizonylatok"):
        """
        Initialize FTP uploader.

        Args:
            host: FTP server hostname
            username: FTP username
            password: FTP password
            port: FTP port (default 21)
            base_path: Base directory on server (default "users/opg_bizonylatok")
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

            # Print current working directory for debugging
            current_dir = self.ftp.pwd()
            print(f"  FTP connected. Current directory: {current_dir}")

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
        Handles both absolute (/path/to/dir) and relative (path/to/dir) paths.

        Args:
            remote_path: Remote directory path (absolute or relative)

        Returns:
            True if directory exists or was created, False otherwise
        """
        # Handle absolute paths
        if remote_path.startswith('/'):
            try:
                # Try to navigate to absolute path
                self.ftp.cwd(remote_path)
                return True
            except:
                # Path doesn't exist, create it recursively
                parts = [p for p in remote_path.split('/') if p]
                self.ftp.cwd('/')  # Start from root

                current_path = ''
                for part in parts:
                    current_path = f"{current_path}/{part}"
                    try:
                        self.ftp.cwd(part)
                    except:
                        try:
                            self.ftp.mkd(part)
                            self.ftp.cwd(part)
                            print(f"  Created directory: {current_path}")
                        except Exception as e:
                            print(f"  Failed to create directory {current_path}: {e}")
                            return False
                return True

        # Handle relative paths
        parts = [p for p in remote_path.split('/') if p]

        if not parts:
            return True

        # Navigate/create each directory level
        current_path = ''
        for part in parts:
            current_path = f"{current_path}/{part}" if current_path else part

            try:
                # Try to change to directory
                self.ftp.cwd(part)
            except:
                # Directory doesn't exist, create it
                try:
                    self.ftp.mkd(part)
                    self.ftp.cwd(part)
                    print(f"  Created directory: {current_path}")
                except Exception as e:
                    print(f"  Failed to create directory {current_path}: {e}")
                    return False

        return True

    def upload_file(self, local_path: Path, remote_dir: str, filename: str) -> bool:
        """
        Upload single file to FTP server.

        Args:
            local_path: Local file path
            remote_dir: Remote directory (relative to base path)
            filename: Remote filename

        Returns:
            True if uploaded successfully, False otherwise
        """
        try:
            # Navigate to base directory (absolute or relative)
            if self.base_path.startswith('/'):
                # Absolute path - navigate directly
                try:
                    self.ftp.cwd(self.base_path)
                except:
                    # Create base path if it doesn't exist
                    print(f"  Base path {self.base_path} doesn't exist, creating...")
                    if not self._ensure_directory(self.base_path):
                        return False
                    self.ftp.cwd(self.base_path)
            else:
                # Relative path - ensure it exists first
                if not self._ensure_directory(self.base_path):
                    return False

            # Ensure target directory exists and navigate to it
            if not self._ensure_directory(remote_dir):
                return False

            # Upload file in binary mode
            with open(local_path, 'rb') as f:
                self.ftp.storbinary(f'STOR {filename}', f)

            full_path = f"{self.base_path}/{remote_dir}/{filename}".replace('//', '/')
            print(f"  Uploaded: {local_path.name} -> {full_path}")
            return True

        except Exception as e:
            print(f"  Failed to upload {local_path.name}: {e}")
            return False

    def upload_xml_files(self, xml_files: List[Path], ap_number: str, year: int) -> Dict:
        """
        Upload multiple XML files to FTP server.

        Directory structure: {base_path}/ap_number/year/
        Example: users/opg_bizonylatok/A29200455/2025/

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
            # Save initial directory
            initial_dir = self.ftp.pwd()
            print(f"  Initial FTP directory: {initial_dir}")

            # Build full target path
            full_target_path = f"{self.base_path}/{ap_number}/{year}"
            print(f"  Target directory: {full_target_path}")

            # Navigate to initial directory
            self.ftp.cwd(initial_dir)

            # Create and navigate to target directory ONCE
            if not self._ensure_directory(full_target_path):
                print(f"  Failed to create target directory: {full_target_path}")
                return result

            # Save the target directory path
            target_dir = self.ftp.pwd()
            print(f"  Successfully navigated to: {target_dir}")

            # Upload each file
            for xml_file in xml_files:
                try:
                    # Navigate to target directory
                    self.ftp.cwd(target_dir)

                    # Upload file
                    with open(xml_file, 'rb') as f:
                        self.ftp.storbinary(f'STOR {xml_file.name}', f)

                    print(f"  Uploaded: {xml_file.name}")
                    result['uploaded'] += 1
                    result['files'].append(xml_file.name)

                except Exception as e:
                    print(f"  Failed to upload {xml_file.name}: {e}")
                    result['failed'] += 1

            result['success'] = result['failed'] == 0

        finally:
            self.disconnect()

        return result


def upload_files_to_ftp(xml_files: List[Path], ap_number: str, year: int,
                        ftp_host: str, ftp_user: str, ftp_password: str,
                        ftp_port: int = 21, ftp_base_path: str = "users/opg_bizonylatok") -> Dict:
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
