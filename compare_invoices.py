#!/usr/bin/env python3
"""
Compare CSV export with Excel export to find differences
"""

import pandas as pd
import sys

def load_csv_export(csv_path):
    """Load CSV export and extract invoice numbers"""
    df = pd.read_csv(csv_path, encoding='utf-8-sig', sep=';')
    print(f"CSV columns: {df.columns.tolist()}")
    print(f"CSV rows: {len(df)}")
    print(f"\nFirst few rows:")
    print(df.head())
    return df

def load_excel_export(excel_path):
    """Load Excel export"""
    df = pd.read_excel(excel_path)
    print(f"\nExcel columns: {df.columns.tolist()}")
    print(f"Excel rows: {len(df)}")
    print(f"\nFirst few rows:")
    print(df.head())
    return df

def main():
    csv_path = '/Users/szuballybruno/Documents/GitHub/opg/2026_01_13_15_40_25_export.csv'
    excel_path = '/Users/szuballybruno/Documents/GitHub/opg/szamlak_bruno_2025_teljesites.xlsx'

    print("=" * 80)
    print("LOADING CSV EXPORT")
    print("=" * 80)
    csv_df = load_csv_export(csv_path)

    print("\n" + "=" * 80)
    print("LOADING EXCEL EXPORT")
    print("=" * 80)
    excel_df = load_excel_export(excel_path)

    # Try to identify invoice number column in CSV
    print("\n" + "=" * 80)
    print("IDENTIFYING COLUMNS")
    print("=" * 80)

    # Common column names for invoice numbers
    csv_invoice_col = None
    for col in csv_df.columns:
        col_lower = col.lower()
        if 'szám' in col_lower or 'number' in col_lower or 'invoice' in col_lower:
            csv_invoice_col = col
            print(f"Found CSV invoice column: {col}")
            break

    # Common column names for amounts
    csv_amount_col = None
    for col in csv_df.columns:
        col_lower = col.lower()
        if 'összeg' in col_lower or 'amount' in col_lower or 'nett' in col_lower:
            csv_amount_col = col
            print(f"Found CSV amount column: {col}")
            break

    if not csv_invoice_col:
        print("WARNING: Could not find invoice number column in CSV")
        print("Available columns:", csv_df.columns.tolist())
        return

    # Extract invoice numbers (remove STORNÓ/MÓDOSÍTÓ markers from Excel)
    print("\n" + "=" * 80)
    print("EXTRACTING INVOICE NUMBERS")
    print("=" * 80)

    csv_invoices = set(csv_df[csv_invoice_col].dropna().astype(str))
    print(f"CSV unique invoices: {len(csv_invoices)}")

    # Clean Excel invoice numbers (remove markers)
    excel_invoices = set()
    for inv in excel_df['Számla száma'].dropna():
        inv_str = str(inv)
        # Remove markers
        inv_clean = inv_str.replace(' (STORNÓ)', '').replace(' (MÓDOSÍTÓ)', '')
        excel_invoices.add(inv_clean)

    print(f"Excel unique invoices: {len(excel_invoices)}")

    # Find differences
    print("\n" + "=" * 80)
    print("COMPARING INVOICE SETS")
    print("=" * 80)

    only_in_csv = csv_invoices - excel_invoices
    only_in_excel = excel_invoices - csv_invoices
    in_both = csv_invoices & excel_invoices

    print(f"\nInvoices in both: {len(in_both)}")
    print(f"Only in CSV: {len(only_in_csv)}")
    print(f"Only in Excel: {len(only_in_excel)}")

    if only_in_csv:
        print(f"\n⚠️  {len(only_in_csv)} invoices ONLY in CSV:")
        for inv in sorted(list(only_in_csv))[:10]:
            print(f"  - {inv}")
        if len(only_in_csv) > 10:
            print(f"  ... and {len(only_in_csv) - 10} more")

    if only_in_excel:
        print(f"\n⚠️  {len(only_in_excel)} invoices ONLY in Excel:")
        for inv in sorted(list(only_in_excel))[:10]:
            print(f"  - {inv}")
        if len(only_in_excel) > 10:
            print(f"  ... and {len(only_in_excel) - 10} more")

    # Compare amounts if column found
    if csv_amount_col:
        print("\n" + "=" * 80)
        print("COMPARING TOTALS")
        print("=" * 80)

        csv_total = csv_df[csv_amount_col].sum()
        excel_total = excel_df['Nettó összeg (HUF)'].sum()

        print(f"CSV total: {csv_total:,.2f} HUF")
        print(f"Excel total: {excel_total:,.2f} HUF")
        print(f"Difference: {excel_total - csv_total:,.2f} HUF")

if __name__ == '__main__':
    main()
