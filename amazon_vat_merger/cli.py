"""CLI: python -m amazon_vat_merger --csv raport.csv --pdf faktury/ --out wynik.xlsx"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from . import __version__
from .excel import write_xlsx
from .invoice_pdf import iter_pdf_paths, parse_pdfs
from .merge import build_sheets, merge
from .nbp import RateProvider
from .report import read_reports

log = logging.getLogger("amazon_vat_merger")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="amazon_vat_merger",
        description="Łączy raport Amazon VAT Transactions (CSV) z fakturami VCS (PDF) w jeden arkusz.",
    )
    p.add_argument("--csv", action="append", required=True, metavar="PLIK", help="raport CSV (można podać wiele razy)")
    p.add_argument("--pdf", action="append", default=[], metavar="PLIK|KATALOG", help="faktura PDF albo katalog z fakturami (rekurencyjnie)")
    p.add_argument("--out", default="output/amazon_vat.xlsx", metavar="PLIK.xlsx", help="plik wynikowy xlsx")
    p.add_argument("--json", metavar="PLIK.json", help="zrzut sparsowanych faktur (diagnostyka)")
    p.add_argument("--sheet-id", metavar="ID|URL", help="ID (lub URL) arkusza Google do nadpisania")
    p.add_argument("--credentials", metavar="klucz.json", help="klucz konta serwisowego Google")
    p.add_argument("--rates-file", metavar="kursy.csv", help="plik kursów: waluta,data,kurs")
    p.add_argument("--no-nbp", action="store_true", help="nie pobieraj kursów z API NBP")
    p.add_argument("--rate-basis", choices=["invoice", "shipment", "order"], default="invoice",
                   help="data bazowa kursu: data faktury (PDF, domyślnie) / wysyłki / zamówienia")
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--version", action="version", version=__version__)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s")

    transactions = read_reports(args.csv)
    if not transactions:
        log.error("brak transakcji w CSV")
        return 2
    known = [t.invoice_number for t in transactions if t.invoice_number]
    pdf_paths = iter_pdf_paths(args.pdf)
    invoices = parse_pdfs(pdf_paths, known)
    rates = RateProvider(use_nbp=not args.no_nbp, rates_file=args.rates_file)
    result = merge(transactions, invoices, rates, rate_basis=args.rate_basis)
    sheets = build_sheets(result)

    out = write_xlsx(args.out, sheets)
    print(f"xlsx: {out}")
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps([i.to_dict() for i in invoices], ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"json: {args.json}")
    if args.sheet_id:
        from .gsheets import push_sheets

        written = push_sheets(args.sheet_id, sheets, credentials_path=args.credentials)
        print(f"Google Sheets: zapisano zakładki: {', '.join(written)}")

    print(
        f"transakcje: {len(result.rows)} | PDF: {len(invoices)} | dopasowane: {result.matched} | "
        f"bez PDF: {result.missing} | PDF bez CSV: {len(result.unmatched_invoices)} | "
        f"zakładki: {', '.join(s.name for s in sheets)}"
    )
    if not rates.nbp_available and not args.no_nbp:
        print(f"UWAGA: API NBP niedostępne ({rates.last_error}) – kolumny PLN bez kursu; użyj --rates-file")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
