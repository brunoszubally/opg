"""
NAV Online Invoice API Client (Python implementation)

This module provides a Python interface for the Hungarian Tax Office (NAV)
Online Invoice Data Reporting system.

Based on the NAV API v3 specification.
"""

import hashlib
import hmac
import base64
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Dict, List, Optional, Any
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
import uuid


class NavOnlineInvoiceConfig:
    """Configuration for NAV Online Invoice API"""

    TEST_URL = "https://api-test.onlineszamla.nav.gov.hu/invoiceService/v3"
    PROD_URL = "https://api.onlineszamla.nav.gov.hu/invoiceService/v3"

    def __init__(self, base_url: str, user_data: Dict[str, str], software_data: Dict[str, str]):
        """
        Initialize configuration

        Args:
            base_url: API endpoint URL (TEST_URL or PROD_URL)
            user_data: User credentials dict with keys:
                - login: Technical user login
                - password: Technical user password (SHA512)
                - taxNumber: Tax number (8 digits)
                - signKey: Signature key
                - exchangeKey: Exchange key for token decryption
            software_data: Software info dict with keys:
                - softwareId: Software identifier
                - softwareName: Software name
                - softwareOperation: Operation type (e.g., ONLINE_SERVICE)
                - softwareMainVersion: Main version
                - softwareDevName: Developer name
                - softwareDevContact: Developer contact
                - softwareDevCountryCode: Developer country (e.g., HU)
                - softwareDevTaxNumber: Developer tax number
        """
        self.base_url = base_url
        self.user = user_data
        self.software = software_data
        self.verify_ssl = True
        self.timeout = 60


class NavOnlineInvoiceConnector:
    """Handles HTTP communication with NAV API"""

    def __init__(self, config: NavOnlineInvoiceConfig):
        self.config = config
        self.last_request_id = None
        self.last_response_xml = None

    def post(self, endpoint: str, request_xml_str: str, request_id: str) -> ET.Element:
        """
        Send POST request to NAV API

        Args:
            endpoint: API endpoint path (e.g., /queryInvoiceDigest)
            request_xml_str: XML request body as string
            request_id: Unique request ID

        Returns:
            Response XML as ElementTree Element

        Raises:
            Exception: If request fails or NAV returns error
        """
        url = self.config.base_url + endpoint
        self.last_request_id = request_id

        headers = {
            'Content-Type': 'application/xml',
            'Accept': 'application/xml'
        }

        response = requests.post(
            url,
            data=request_xml_str.encode('utf-8'),
            headers=headers,
            verify=self.config.verify_ssl,
            timeout=self.config.timeout
        )

        if response.status_code != 200:
            raise Exception(f"HTTP {response.status_code}: {response.text}")

        # Parse response XML
        root = ET.fromstring(response.content)
        self.last_response_xml = root

        # Check for NAV API errors
        result_elem = root.find('.//{*}result')
        if result_elem is not None:
            func_code = result_elem.find('.//{*}funcCode')
            if func_code is not None and func_code.text != 'OK':
                error_code = result_elem.find('.//{*}errorCode')
                message = result_elem.find('.//{*}message')
                error_msg = f"NAV API Error: {error_code.text if error_code is not None else 'Unknown'}"
                if message is not None:
                    error_msg += f" - {message.text}"
                raise Exception(error_msg)

        return root


class NavOnlineInvoiceReporter:
    """Main class for interacting with NAV Online Invoice API"""

    def __init__(self, config: NavOnlineInvoiceConfig):
        self.config = config
        self.connector = NavOnlineInvoiceConnector(config)

    def _generate_request_id(self) -> str:
        """Generate unique request ID (RID followed by timestamp)"""
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S%f')[:-3]  # milliseconds
        return f"RID{timestamp}{uuid.uuid4().hex[:10]}"

    def _get_timestamp(self) -> str:
        """
        Get current timestamp in NAV format with milliseconds
        Format: YYYY-MM-DDTHH:MM:SS.sssZ (UTC)
        """
        now = datetime.utcnow()
        millis = now.microsecond // 1000
        return f"{now.strftime('%Y-%m-%dT%H:%M:%S')}.{millis:03d}Z"

    def _create_request_signature(self, request_id: str, timestamp: str) -> str:
        """
        Create request signature using SHA3-512

        Args:
            request_id: Unique request identifier
            timestamp: NAV timestamp with milliseconds

        Returns:
            Hex encoded signature (uppercase)
        """
        # Remove milliseconds and non-digits from timestamp for signature
        # Format: yyyyMMddHHmmss (14 digits)
        import re
        timestamp_clean = re.sub(r'\.\d{3}|\D+', '', timestamp)

        # Concatenate: requestId + timestamp (without millis) + signKey
        data = f"{request_id}{timestamp_clean}{self.config.user['signKey']}"

        # SHA3-512 hash
        hash_obj = hashlib.sha3_512(data.encode('utf-8'))
        signature = hash_obj.hexdigest().upper()

        return signature

    def _build_common_header(self, request_id: str, timestamp: str) -> ET.Element:
        """Build common header for all requests"""
        header = ET.Element('header')

        ET.SubElement(header, 'requestId').text = request_id
        ET.SubElement(header, 'timestamp').text = timestamp
        ET.SubElement(header, 'requestVersion').text = '3.0'
        ET.SubElement(header, 'headerVersion').text = '1.0'

        return header

    def _build_user_element(self, request_id: str, timestamp: str) -> ET.Element:
        """Build user authentication element"""
        user = ET.Element('user')

        ET.SubElement(user, 'login').text = self.config.user['login']

        # Password hash: SHA-512(password)
        password_hash = hashlib.sha512(self.config.user['password'].encode('utf-8')).hexdigest().upper()
        password_hash_elem = ET.SubElement(user, 'passwordHash')
        password_hash_elem.text = password_hash
        password_hash_elem.set('cryptoType', 'SHA-512')

        ET.SubElement(user, 'taxNumber').text = self.config.user['taxNumber']

        # Request signature (SHA3-512)
        signature = self._create_request_signature(request_id, timestamp)
        signature_elem = ET.SubElement(user, 'requestSignature')
        signature_elem.text = signature
        signature_elem.set('cryptoType', 'SHA3-512')

        return user

    def _build_software_element(self) -> ET.Element:
        """Build software identification element"""
        software = ET.Element('software')

        for key, value in self.config.software.items():
            ET.SubElement(software, key).text = str(value)

        return software

    def query_invoice_digest(
        self,
        invoice_query_params: Dict[str, Any],
        page: int = 1,
        direction: str = "OUTBOUND"
    ) -> Dict[str, Any]:
        """
        Query invoice digest (summary list of invoices)

        Args:
            invoice_query_params: Query parameters dict with structure:
                {
                    "mandatoryQueryParams": {
                        "invoiceIssueDate": {
                            "dateFrom": "2025-01-01",
                            "dateTo": "2025-01-31"
                        }
                    }
                }
            page: Page number (1-indexed)
            direction: Invoice direction ("OUTBOUND" or "INBOUND")

        Returns:
            Dict with invoice digest results:
                {
                    "currentPage": 1,
                    "availablePage": 5,
                    "invoiceDigest": [...]
                }
        """
        request_id = self._generate_request_id()
        timestamp = self._get_timestamp()

        # Build XML request with proper namespaces
        # Root element
        root = ET.Element('QueryInvoiceDigestRequest')
        root.set('xmlns', 'http://schemas.nav.gov.hu/OSA/3.0/api')
        root.set('xmlns:common', 'http://schemas.nav.gov.hu/NTCA/1.0/common')

        # Add common elements (with common: namespace prefix)
        header = self._build_common_header(request_id, timestamp)
        # Re-register all children with common namespace
        for child in header:
            child.tag = f'{{http://schemas.nav.gov.hu/NTCA/1.0/common}}{child.tag}'
        header.tag = '{http://schemas.nav.gov.hu/NTCA/1.0/common}header'
        root.append(header)

        user = self._build_user_element(request_id, timestamp)
        # Re-register all children with common namespace
        for child in user:
            child.tag = f'{{http://schemas.nav.gov.hu/NTCA/1.0/common}}{child.tag}'
        user.tag = '{http://schemas.nav.gov.hu/NTCA/1.0/common}user'
        root.append(user)

        software = self._build_software_element()
        root.append(software)

        # Add page
        ET.SubElement(root, 'page').text = str(page)

        # Add invoice direction
        ET.SubElement(root, 'invoiceDirection').text = direction

        # Add query params
        query_params_elem = ET.SubElement(root, 'invoiceQueryParams')
        self._dict_to_xml(invoice_query_params, query_params_elem)

        # Convert to string
        xml_str = ET.tostring(root, encoding='utf-8', xml_declaration=True).decode('utf-8')

        # Send request
        response_root = self.connector.post('/queryInvoiceDigest', xml_str, request_id)

        # Parse response
        result = {}

        # Find invoiceDigestResult element
        digest_result = response_root.find('.//{*}invoiceDigestResult')
        if digest_result is not None:
            current_page = digest_result.find('.//{*}currentPage')
            available_page = digest_result.find('.//{*}availablePage')

            result['currentPage'] = int(current_page.text) if current_page is not None else page
            result['availablePage'] = int(available_page.text) if available_page is not None else page

            # Parse invoice digest items
            invoices = []
            for digest_elem in digest_result.findall('.//{*}invoiceDigest'):
                invoice = self._xml_to_dict(digest_elem)
                invoices.append(invoice)

            result['invoiceDigest'] = invoices

        return result

    def _dict_to_xml(self, data: Dict[str, Any], parent: ET.Element):
        """Convert dict to XML elements recursively"""
        for key, value in data.items():
            if isinstance(value, dict):
                child = ET.SubElement(parent, key)
                self._dict_to_xml(value, child)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        child = ET.SubElement(parent, key)
                        self._dict_to_xml(item, child)
                    else:
                        ET.SubElement(parent, key).text = str(item)
            else:
                ET.SubElement(parent, key).text = str(value)

    def _xml_to_dict(self, element: ET.Element) -> Dict[str, Any]:
        """Convert XML element to dict recursively"""
        result = {}

        # Get tag name without namespace
        tag = element.tag.split('}')[-1] if '}' in element.tag else element.tag

        # If element has children, recurse
        if len(element):
            for child in element:
                child_tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                child_data = self._xml_to_dict(child)

                # Handle multiple children with same tag
                if child_tag in result:
                    if not isinstance(result[child_tag], list):
                        result[child_tag] = [result[child_tag]]
                    result[child_tag].append(child_data)
                else:
                    result[child_tag] = child_data
        else:
            # Leaf node - return text content
            return element.text

        return result


def normalize_tax_number(raw_tax_number: str) -> Optional[str]:
    """
    Normalize Hungarian tax number to 8 digits

    Args:
        raw_tax_number: Raw tax number (may include HU prefix, dashes, etc.)

    Returns:
        8-digit tax number or None if invalid
    """
    import re

    s = raw_tax_number.upper().strip()

    # Remove HU prefix
    if s.startswith('HU'):
        s = s[2:]

    # Find first 8 consecutive digits
    match = re.search(r'(\d{8})', s)
    if match:
        return match.group(1)

    # Remove all non-digits and take first 8
    only_digits = re.sub(r'\D+', '', s)
    if len(only_digits) >= 8:
        return only_digits[:8]

    return None
