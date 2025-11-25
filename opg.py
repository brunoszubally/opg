#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse, datetime as dt, hashlib, uuid, requests, os, re, zipfile, subprocess
from pathlib import Path

# ==== CRED: hardcoded hitelesítési adatok ===============
TECH_LOGIN      = "nmcmmjt4fpsy93v"
TECH_PASSWORD   = "Zsufeh21"
# Próbáljuk az EREDETI signKey-t KÖTŐJELEKKEL!
SIGNING_KEY     = "7f-835d-e344a049c0284XU5VHIADWAT"  # signKey EREDETI formátum (XML kulcs)
EXCHANGE_KEY    = "2de64XU5VHIACOB2"  # exchangeKey (XML cserekulcs)
TAX_NUMBER_8DIG = "69785346"  # Az API dokumentáció szerint csak az első 8 számjegy kell
# Teljes adószám: 69785346-1-29 (de az API-nak csak az első 8 számjegyet kell küldeni)
AP_NUMBER       = "A29200455"  # az általad használt AP szám

# ÉLES végpontok
BASE = "https://api-onlinepenztargep.nav.gov.hu"
# Namespace-ek a minta XML alapján
NS_API = "http://schemas.nav.gov.hu/OPF/1.0/api"
NS_COM = "http://schemas.nav.gov.hu/NTCA/1.0/common"

# ---- Hash segédek ----
def sha512_upper(s: str) -> str:
    import hashlib
    return hashlib.sha512(s.encode("utf-8")).hexdigest().upper()

def sha3_512_upper(s: str) -> str:
    import hashlib
    return hashlib.sha3_512(s.encode("utf-8")).hexdigest().upper()

def now_utc_compact() -> str:
    # A NAV példában ISO 8601 formátum van, nem kompakt!
    # Példa: 2022-02-01T11:40:44.037Z
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")[:-4] + "Z"  # mikroszekundumból milliszekundum

def make_headers():
    # SOAP 1.2 használ application/soap+xml-t
    return {
        "Content-Type": "application/soap+xml; charset=utf-8",
        "Accept": "application/soap+xml, application/xml, text/xml, */*"
    }

# ---- SOAP blokkok ----
def software_block(dev_name="Bruno Szubally", dev_contact="info@example.com", dev_tax="77317012"):
    return f"""
    <api:software>
      <api:softwareId>HU77317012-PYOPGCL</api:softwareId>
      <api:softwareName>Python OPG Client</api:softwareName>
      <api:softwareOperation>LOCAL_SOFTWARE</api:softwareOperation>
      <api:softwareMainVersion>1.0</api:softwareMainVersion>
      <api:softwareDevName>{dev_name}</api:softwareDevName>
      <api:softwareDevContact>{dev_contact}</api:softwareDevContact>
      <api:softwareDevCountryCode>HU</api:softwareDevCountryCode>
      <api:softwareDevTaxNumber>{dev_tax}</api:softwareDevTaxNumber>
    </api:software>"""

def user_block(request_id: str, timestamp: str, use_exchange_key=False, debug=False):
    if not (TECH_LOGIN and TECH_PASSWORD and TAX_NUMBER_8DIG):
        raise RuntimeError("Hiányos hitelesítési adatok.")
    pwd_hash = sha512_upper(TECH_PASSWORD)
    # Próbáljuk meg mindkét kulcsot
    key_to_use = EXCHANGE_KEY if use_exchange_key else SIGNING_KEY
    # Issue #66: signature számításhoz CSAK MÁSODPERC pontosságú timestamp!
    # A timestamp paraméter milliszekundumokat tartalmaz (XML-hez), de a signature-höz
    # másodperc pontosságú verziót kell használni
    import re
    # Levágjuk a milliszekundumokat: 2022-02-01T11:40:44.037Z -> 2022-02-01T11:40:44Z
    timestamp_seconds_only = re.sub(r'\.\d+Z$', 'Z', timestamp)
    # Tisztítjuk: eltávolítjuk - : Z T karaktereket (kell: YYYYMMDDHHMMSS, 14 karakter)
    timestamp_for_sig = timestamp_seconds_only.replace("-","").replace(":","").replace("Z","").replace("T","")
    req_sig  = sha3_512_upper(request_id + timestamp_for_sig + key_to_use)
    if debug:
        print(f"DEBUG: Signature kulcs: {key_to_use}")
        print(f"DEBUG: Timestamp XML-ben: {timestamp}")
        print(f"DEBUG: Timestamp másodperc: {timestamp_seconds_only}")
        print(f"DEBUG: Timestamp signature-höz: {timestamp_for_sig} (hossz: {len(timestamp_for_sig)})")
        print(f"DEBUG: Signature bemenet: {request_id + timestamp_for_sig + key_to_use}")
        print(f"DEBUG: Signature: {req_sig}")
    return f"""
    <com:user>
      <com:login>{TECH_LOGIN}</com:login>
      <com:passwordHash cryptoType="SHA-512">{pwd_hash}</com:passwordHash>
      <com:taxNumber>{TAX_NUMBER_8DIG}</com:taxNumber>
      <com:requestSignature cryptoType="SHA3-512">{req_sig}</com:requestSignature>
    </com:user>"""

def header_block(request_id: str, timestamp: str):
    return f"""
    <com:header>
      <com:requestId>{request_id}</com:requestId>
      <com:timestamp>{timestamp}</com:timestamp>
      <com:requestVersion>1.0</com:requestVersion>
      <com:headerVersion>1.0</com:headerVersion>
    </com:header>"""

def envelope(inner_xml: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope" xmlns:api="{NS_API}" xmlns:com="{NS_COM}">
  <soap:Header/>
  <soap:Body>
{inner_xml}
  </soap:Body>
</soap:Envelope>"""

def build_status_xml(ap: str | None, use_exchange_key=False, debug=False):
    # requestId: max 30 karakter, pattern: [+a-zA-Z0-9_]{1,30}
    rid = str(uuid.uuid4()).replace("-", "")[:30]  # UUID kötőjelek nélkül, max 30 kar
    ts = now_utc_compact()
    ap_xml = f"""
    <api:cashRegisterStatusQuery>
      <api:APNumberList>
        <api:APNumber>{ap}</api:APNumber>
      </api:APNumberList>
    </api:cashRegisterStatusQuery>""" if ap else ""
    body = f"""    <api:QueryCashRegisterStatusRequest>
{header_block(rid, ts)}
{user_block(rid, ts, use_exchange_key, debug)}
{software_block()}
{ap_xml}
    </api:QueryCashRegisterStatusRequest>"""
    return envelope(body)

def build_file_xml(ap: str, start: int, end: int | None, debug=False):
    # requestId: max 30 karakter, pattern: [+a-zA-Z0-9_]{1,30}
    rid = str(uuid.uuid4()).replace("-", "")[:30]  # UUID kötőjelek nélkül, max 30 kar
    ts = now_utc_compact()
    end_xml = f"        <api:fileNumberEnd>{end}</api:fileNumberEnd>" if end else ""
    body = f"""    <api:QueryCashRegisterFileDataRequest>
{header_block(rid, ts)}
{user_block(rid, ts, False, debug)}
{software_block()}
      <api:cashRegisterFileDataQuery>
        <api:APNumber>{ap}</api:APNumber>
        <api:fileNumberStart>{start}</api:fileNumberStart>
{end_xml}
      </api:cashRegisterFileDataQuery>
    </api:QueryCashRegisterFileDataRequest>"""
    return envelope(body)

def post_xml(url: str, xml: str) -> requests.Response:
    return requests.post(url, data=xml.encode("utf-8"), headers=make_headers(), timeout=120)

def parse_status_response(response_text: str) -> dict | None:
    """Parse status response and extract min/max file numbers."""
    func_code = re.search(r'<ns2:funcCode>(.*?)</ns2:funcCode>', response_text)
    if not func_code or func_code.group(1) != "OK":
        return None

    min_file = re.search(r'<ns3:minAvailableFileNumber>(.*?)</ns3:minAvailableFileNumber>', response_text)
    max_file = re.search(r'<ns3:maxAvailableFileNumber>(.*?)</ns3:maxAvailableFileNumber>', response_text)
    ap_num = re.search(r'<ns3:APNumber>(.*?)</ns3:APNumber>', response_text)

    if min_file and max_file:
        return {
            'min': int(min_file.group(1)),
            'max': int(max_file.group(1)),
            'ap': ap_num.group(1) if ap_num else None
        }
    return None

# ---- MTOM/multipart mentés (ZIP mellékletek) ----
def save_mtom_attachments(resp: requests.Response, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    ctype = resp.headers.get("Content-Type", "")
    if "multipart/related" not in ctype.lower():
        (out_dir / "response.xml").write_bytes(resp.content)
        return []
    m = re.search(r'boundary="?([^";]+)"?', ctype, flags=re.I)
    if not m:
        raise RuntimeError("Nem találtam boundary-t a Content-Type fejlécben.")
    boundary = m.group(1)
    parts = resp.content.split(("--" + boundary).encode())
    saved: list[Path] = []
    idx = 0
    for part in parts:
        part = part.strip()
        if not part or part == b'--':
            continue
        header_end = part.find(b"\r\n\r\n")
        if header_end < 0: header_end = part.find(b"\n\n")
        if header_end < 0:  continue
        header = part[:header_end].decode("utf-8", errors="ignore")
        body   = part[header_end + (4 if part[header_end:header_end+4]==b'\r\n\r\n' else 2):]
        if "application/octet-stream" in header.lower() or "application/zip" in header.lower():
            name = None
            m2 = re.search(r'name="?([^";]+)"?', header, flags=re.I)
            if m2: name = m2.group(1)
            if not name: name = f"attachment_{idx}.zip"
            if not name.lower().endswith(".zip"): name += ".zip"
            out_file = out_dir / name
            out_file.write_bytes(body)
            saved.append(out_file); idx += 1
    return saved

def unzip_all(zip_path: Path, dest_root: Path) -> list[Path]:
    extracted: list[Path] = []
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(dest_root)
        for n in z.namelist():
            extracted.append(dest_root / n)
    return extracted

# ---- P7B extraction (from extract_p7b.py) ----
def try_openssl_cms(p7b_path: Path) -> str | None:
    """OpenSSL CMS parancs használata a tartalom kinyerésére."""
    try:
        result = subprocess.run(
            ["openssl", "cms", "-in", str(p7b_path), "-inform", "DER", "-verify", "-noverify"],
            capture_output=True, text=False, timeout=10
        )
        if result.returncode == 0 and result.stdout:
            try:
                decoded = result.stdout.decode('utf-8')
                if '<?xml' in decoded:
                    return decoded
            except UnicodeDecodeError:
                pass
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
        pass
    return None

def extract_xml_from_binary(p7b_path: Path) -> str | None:
    """Regex-alapú XML kinyerés közvetlenül a bináris fájlból."""
    try:
        content = p7b_path.read_bytes()
        content_str = content.decode('utf-8', errors='ignore')
        # NAV OPG XML-ek <ROWS> root elemmel
        xml_match = re.search(
            r'(<\?xml[^>]*\?>.*?<ROWS\b[^>]*>.*?</ROWS>)',
            content_str, re.DOTALL | re.IGNORECASE
        )
        if xml_match:
            return xml_match.group(1)
        # Általánosabb pattern
        root_search = re.search(r'<\?xml[^>]*\?>\s*<([A-Z][A-Za-z0-9_]*)\b', content_str)
        if root_search:
            root_tag = root_search.group(1)
            xml_match = re.search(
                rf'(<\?xml[^>]*\?>.*?<{root_tag}\b[^>]*>.*?</{root_tag}>)',
                content_str, re.DOTALL | re.IGNORECASE
            )
            if xml_match:
                return xml_match.group(1)
    except Exception:
        pass
    return None

def extract_p7b_to_xml(p7b_path: Path, output_path: Path | None = None, verbose: bool = False) -> bool:
    """P7B fájl tartalmának kinyerése XML-be."""
    if not p7b_path.exists():
        return False

    # OpenSSL próba
    xml_content = try_openssl_cms(p7b_path)
    method = "OpenSSL"
    if not xml_content:
        # Regex próba
        xml_content = extract_xml_from_binary(p7b_path)
        method = "Regex"

    if not xml_content:
        if verbose:
            print(f"  ✗ Nem sikerült kinyerni: {p7b_path.name}")
        return False

    if output_path is None:
        output_path = p7b_path.with_suffix('.xml')

    output_path.write_text(xml_content, encoding='utf-8')
    if verbose:
        size = len(xml_content.encode('utf-8'))
        print(f"  ✓ {p7b_path.name} → {output_path.name} ({method}, {size:,} bytes)")
    return True

def main():
    ap = argparse.ArgumentParser(description="NAV Online Pénztárgép (éles) – státusz és naplófájl letöltés")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("status", help="Pénztárgép státusz lekérdezése (min/max FileNumber)")
    p1.add_argument("--ap", help="Konkrét APNumber (pl. AX12345678)")
    p1.add_argument("--use-exchange-key", action="store_true", help="EXCHANGE_KEY használata SIGNING_KEY helyett")
    p1.add_argument("--debug", action="store_true", help="Debug információk megjelenítése")

    p2 = sub.add_parser("files", help="Naplófájlok letöltése és ZIP-ek mentése")
    p2.add_argument("--ap", required=True, help="APNumber (pl. AX12345678)")
    p2.add_argument("--start", type=int, required=True, help="FileNumberStart")
    p2.add_argument("--end", type=int, help="FileNumberEnd")
    p2.add_argument("--out", default="./opg_out", help="Mentési mappa")
    p2.add_argument("--debug", action="store_true", help="Debug információk megjelenítése")

    p3 = sub.add_parser("download-all", help="Összes elérhető fájl letöltése és XML kinyerés")
    p3.add_argument("--ap", required=True, help="APNumber (pl. AX12345678)")
    p3.add_argument("--out", default="./opg_downloads", help="Mentési mappa")
    p3.add_argument("--debug", action="store_true", help="Debug információk megjelenítése")
    p3.add_argument("--use-exchange-key", action="store_true", help="EXCHANGE_KEY használata SIGNING_KEY helyett")

    args = ap.parse_args()

    if args.cmd == "status":
        use_exchange = getattr(args, 'use_exchange_key', False)
        debug = getattr(args, 'debug', False)
        xml = build_status_xml(args.ap, use_exchange_key=use_exchange, debug=debug)
        url = f"{BASE}/queryCashRegisterFile/v1/queryCashRegisterStatus"

        if debug:
            print("=== KÜLDÖTT XML ===")
            print(xml)
            print(f"\n=== VÁLASZ ({url}) ===")

        r = post_xml(url, xml)

        if debug:
            print("HTTP:", r.status_code)
            print("Headers:", dict(r.headers))
            print("\nBody:")
            print(r.text)
        else:
            # Parse és print a lényeg
            import re
            if r.status_code == 200 and "funcCode" in r.text:
                func_code = re.search(r'<ns2:funcCode>(.*?)</ns2:funcCode>', r.text)
                if func_code and func_code.group(1) == "OK":
                    print("✓ Státusz lekérdezés sikeres")
                    ap_num = re.search(r'<ns3:APNumber>(.*?)</ns3:APNumber>', r.text)
                    min_file = re.search(r'<ns3:minAvailableFileNumber>(.*?)</ns3:minAvailableFileNumber>', r.text)
                    max_file = re.search(r'<ns3:maxAvailableFileNumber>(.*?)</ns3:maxAvailableFileNumber>', r.text)
                    last_comm = re.search(r'<ns3:lastCommunicationDate>(.*?)</ns3:lastCommunicationDate>', r.text)
                    last_file = re.search(r'<ns3:lastFileDate>(.*?)</ns3:lastFileDate>', r.text)

                    if ap_num:
                        print(f"  AP szám: {ap_num.group(1)}")
                    if last_comm:
                        print(f"  Utolsó kommunikáció: {last_comm.group(1)}")
                    if last_file:
                        print(f"  Utolsó fájl dátuma: {last_file.group(1)}")
                    if min_file and max_file:
                        print(f"  Elérhető fájlok: {min_file.group(1)} - {max_file.group(1)} ({int(max_file.group(1)) - int(min_file.group(1)) + 1} db)")
                else:
                    print("✗ Hiba:")
                    error_code = re.search(r'<ns2:errorCode>(.*?)</ns2:errorCode>', r.text)
                    message = re.search(r'<ns2:message>(.*?)</ns2:message>', r.text)
                    if error_code:
                        print(f"  Error code: {error_code.group(1)}")
                    if message:
                        print(f"  Message: {message.group(1)}")
            else:
                print(f"✗ HTTP hiba: {r.status_code}")
                print(r.text[:500])
        return

    if args.cmd == "files":
        debug = getattr(args, 'debug', False)
        out_dir = Path(args.out); out_dir.mkdir(parents=True, exist_ok=True)
        xml = build_file_xml(args.ap, args.start, args.end, debug=debug)
        url = f"{BASE}/queryCashRegisterFile/v1/queryCashRegisterFile"

        if debug:
            print("=== KÜLDÖTT XML ===")
            print(xml)
            print(f"\n=== KÜLDÉS IDE: {url} ===")

        r = post_xml(url, xml)

        if debug:
            print("HTTP:", r.status_code)
            print("Response Headers:", dict(r.headers))
            if r.status_code != 200:
                print("Response Body:", r.text[:1000])
            (out_dir / "response_raw.txt").write_bytes(r.content)
            print(f"Nyers válasz elmentve: {out_dir / 'response_raw.txt'} ({len(r.content)} bytes)")

        if r.status_code != 200:
            print(f"✗ HTTP hiba: {r.status_code}")
            return

        attachments = save_mtom_attachments(r, out_dir)
        if not attachments:
            print("✗ Nem jött melléklet. Ellenőrizd a FileNumber tartományt.")
            return

        print(f"✓ Sikeresen letöltve {len(attachments)} fájl")

        # Kibontás
        p7b_files = []
        for z in attachments:
            target = out_dir / (z.stem + "_unzipped")
            files = unzip_all(z, target)
            for f in files:
                if f.suffix == '.p7b':
                    p7b_files.append(f)
                    if debug:
                        print(f"  • {f.name}")

        if not debug:
            print(f"  Mentve: {out_dir}/")
            print(f"  P7B fájlok: {len(p7b_files)} db")

    if args.cmd == "download-all":
        debug = getattr(args, 'debug', False)
        use_exchange = getattr(args, 'use_exchange_key', False)
        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)

        # 1. Státusz lekérdezés
        print("📋 Státusz lekérdezése...")
        xml = build_status_xml(args.ap, use_exchange_key=use_exchange, debug=debug)
        url = f"{BASE}/queryCashRegisterFile/v1/queryCashRegisterStatus"
        r = post_xml(url, xml)

        if r.status_code != 200:
            print(f"✗ HTTP hiba: {r.status_code}")
            return

        status = parse_status_response(r.text)
        if not status:
            print("✗ Státusz lekérdezés sikertelen")
            if debug:
                print(r.text[:500])
            return

        print(f"✓ Elérhető fájlok: {status['min']} - {status['max']} ({status['max'] - status['min'] + 1} db)")

        # 2. Fájlok letöltése
        print("\n📥 Fájlok letöltése...")
        xml = build_file_xml(args.ap, status['min'], status['max'], debug=debug)
        url = f"{BASE}/queryCashRegisterFile/v1/queryCashRegisterFile"
        r = post_xml(url, xml)

        if r.status_code != 200:
            print(f"✗ HTTP hiba: {r.status_code}")
            return

        attachments = save_mtom_attachments(r, out_dir)
        if not attachments:
            print("✗ Nem jött melléklet")
            return

        print(f"✓ Letöltve {len(attachments)} ZIP fájl")

        # 3. ZIP kibontás és P7B gyűjtés
        print("\n📦 ZIP fájlok kibontása...")
        p7b_files = []
        for z in attachments:
            target = out_dir / (z.stem + "_unzipped")
            files = unzip_all(z, target)
            for f in files:
                if f.suffix == '.p7b':
                    p7b_files.append(f)

        print(f"✓ Kibontva {len(p7b_files)} P7B fájl")

        # 4. XML kinyerés
        print("\n📄 XML kinyerés P7B fájlokból...")
        success_count = 0
        for p7b in p7b_files:
            if extract_p7b_to_xml(p7b, verbose=debug):
                success_count += 1

        print(f"✓ Sikeresen kinyerve {success_count}/{len(p7b_files)} XML fájl")
        print(f"\n✅ Kész! Fájlok helye: {out_dir}/")

if __name__ == "__main__":
    main()
