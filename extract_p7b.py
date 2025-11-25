#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P7B (PKCS#7) fájlok tartalmának kinyerése

A P7B fájlok aláírt XML konténerek. Ez a script több módszerrel próbálja meg
kinyerni az XML tartalmat:
1. OpenSSL cms parancs (ha elérhető)
2. Regex-alapú bináris kinyerés (ha OpenSSL nem működik)
"""

import sys
import subprocess
import re
from pathlib import Path

def try_openssl_cms(p7b_path: Path) -> str | None:
    """
    OpenSSL CMS parancs használata a tartalom kinyerésére.
    Issue #62 szerint lehet, hogy nem működik tanúsítvány nélkül.
    """
    try:
        # 1. Próba: -noverify (legvalószínűbb hogy működik)
        result = subprocess.run(
            ["openssl", "cms", "-in", str(p7b_path), "-inform", "DER", "-verify", "-noverify"],
            capture_output=True,
            text=False,  # bytes
            timeout=10
        )
        if result.returncode == 0 and result.stdout:
            # Próbáljuk UTF-8-ként dekódolni
            try:
                decoded = result.stdout.decode('utf-8')
                if '<?xml' in decoded:
                    return decoded
            except UnicodeDecodeError:
                pass

        # 2. Próba: -noout nélkül csak a tartalmat írja ki
        result = subprocess.run(
            ["openssl", "cms", "-in", str(p7b_path), "-inform", "DER", "-verify", "-noverify", "-out", "-"],
            capture_output=True,
            text=False,
            timeout=10
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
    """
    Regex-alapú XML kinyerés közvetlenül a bináris fájlból.
    Issue #62 szerint ez gyakran működik amikor az OpenSSL nem.
    """
    try:
        content = p7b_path.read_bytes()
        # Az XML valószínűleg UTF-8 kódolású
        content_str = content.decode('utf-8', errors='ignore')

        # A NAV OPG XML-ek <ROWS> root elemmel rendelkeznek
        # Keressük meg: <?xml...?><ROWS...>...</ROWS>
        xml_match = re.search(
            r'(<\?xml[^>]*\?>.*?<ROWS\b[^>]*>.*?</ROWS>)',
            content_str,
            re.DOTALL | re.IGNORECASE
        )
        if xml_match:
            return xml_match.group(1)

        # Ha nem találtuk, próbáljunk általánosabb patternt
        # Keressük a root elem nevét és találjuk meg a záró taget
        root_search = re.search(r'<\?xml[^>]*\?>\s*<([A-Z][A-Za-z0-9_]*)\b', content_str)
        if root_search:
            root_tag = root_search.group(1)
            xml_match = re.search(
                rf'(<\?xml[^>]*\?>.*?<{root_tag}\b[^>]*>.*?</{root_tag}>)',
                content_str,
                re.DOTALL | re.IGNORECASE
            )
            if xml_match:
                return xml_match.group(1)

    except Exception as e:
        print(f"  Hiba a bináris feldolgozás során: {e}")
    return None

def extract_p7b(p7b_path: Path, output_path: Path | None = None) -> bool:
    """
    P7B fájl tartalmának kinyerése.

    Args:
        p7b_path: A P7B fájl elérési útja
        output_path: A kimenet elérési útja (opcionális)

    Returns:
        True ha sikeres, False egyébként
    """
    if not p7b_path.exists():
        print(f"✗ Fájl nem található: {p7b_path}")
        return False

    print(f"Feldolgozás: {p7b_path.name}")

    # 1. Próbálkozás: OpenSSL
    xml_content = try_openssl_cms(p7b_path)
    if xml_content:
        print("  ✓ OpenSSL CMS sikeresen kinyerte a tartalmat")
    else:
        print("  ⚠ OpenSSL CMS nem működött, próbálkozás regex-szel...")
        # 2. Próbálkozás: Regex
        xml_content = extract_xml_from_binary(p7b_path)
        if xml_content:
            print("  ✓ Regex-alapú kinyerés sikeres")
        else:
            print("  ✗ Nem sikerült kinyerni a tartalmat")
            return False

    # Kimenet mentése
    if output_path is None:
        output_path = p7b_path.with_suffix('.xml')

    output_path.write_text(xml_content, encoding='utf-8')
    print(f"  → Mentve: {output_path}")

    # Statisztika
    lines = len(xml_content.splitlines())
    size = len(xml_content.encode('utf-8'))
    print(f"  Méret: {size:,} bytes, {lines} sor")

    return True

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="P7B (PKCS#7) fájlok XML tartalmának kinyerése"
    )
    parser.add_argument("files", nargs="+", help="P7B fájlok (egy vagy több)")
    parser.add_argument("--out-dir", help="Kimeneti mappa (alapértelmezés: P7B fájl mellett)")

    args = parser.parse_args()

    success_count = 0
    fail_count = 0

    for file_path_str in args.files:
        p7b_path = Path(file_path_str)

        if args.out_dir:
            output_path = Path(args.out_dir) / p7b_path.with_suffix('.xml').name
            Path(args.out_dir).mkdir(parents=True, exist_ok=True)
        else:
            output_path = None

        if extract_p7b(p7b_path, output_path):
            success_count += 1
        else:
            fail_count += 1
        print()

    print("=" * 60)
    print(f"✓ Sikeres: {success_count}")
    if fail_count > 0:
        print(f"✗ Sikertelen: {fail_count}")

if __name__ == "__main__":
    if len(sys.argv) == 1:
        print("Használat: python3 extract_p7b.py <p7b_fájl> [<p7b_fájl> ...]")
        print("Példa:     python3 extract_p7b.py opg_downloads/*/A*.p7b")
        print("           python3 extract_p7b.py file.p7b --out-dir ./xml_files")
        sys.exit(1)
    main()
