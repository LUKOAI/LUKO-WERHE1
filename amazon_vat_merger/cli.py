"""CLI: python -m amazon_vat_merger --csv raport.csv --pdf faktury/ --out wynik.xlsx"""
from __future__ import annotations

import argparse
import logging
import sys

from . import APP_NAME, __version__
from .job import run_job

log = logging.getLogger("amazon_vat_merger")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="amazon_vat_merger",
        description=f"{APP_NAME}: łączy raport Amazon VAT Transactions (CSV) z fakturami VCS (PDF) w jeden arkusz.",
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
                   help="data bazowa kursu: wcześniejsza z dat faktury (PDF) i wysyłki (domyślnie) / wysyłki / zamówienia")
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s")
    try:
        job = run_job(
            csv_paths=args.csv, pdf_sources=args.pdf, out_path=args.out, rates_file=args.rates_file,
            use_nbp=not args.no_nbp, rate_basis=args.rate_basis, sheet_id=args.sheet_id,
            credentials=args.credentials, json_dump=args.json,
        )
    except ValueError as exc:
        log.error("%s", exc)
        return 2
    print(f"xlsx: {job.xlsx_path}")
    if args.json:
        print(f"json: {args.json}")
    if job.pushed_tabs:
        print(f"Google Sheets: zapisano zakładki: {', '.join(job.pushed_tabs)}")
    r = job.result
    print(
        f"transakcje: {len(r.rows)} | PDF: {len(r.invoices)} | dopasowane: {r.matched} | "
        f"bez PDF: {r.missing} | PDF bez CSV: {len(r.unmatched_invoices)} | "
        f"zakładki: {', '.join(job.sheets)}"
    )
    if job.nbp_error:
        print(f"UWAGA: API NBP niedostępne ({job.nbp_error}) – kolumny PLN bez kursu; użyj --rates-file")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
