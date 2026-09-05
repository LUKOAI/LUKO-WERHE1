"""Jedno uruchomienie przetwarzania (wspólne dla CLI i GUI)."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .excel import write_xlsx
from .invoice_pdf import iter_pdf_paths, parse_pdfs
from .merge import MergeResult, build_sheets, merge
from .nbp import RateProvider
from .report import read_reports

log = logging.getLogger("amazon_vat_merger")


@dataclass
class JobResult:
    xlsx_path: Path
    result: MergeResult
    sheets: list[str]
    pushed_tabs: list[str] = field(default_factory=list)
    nbp_error: str | None = None

    @property
    def summary(self) -> str:
        r = self.result
        s = (f"transakcje: {len(r.rows)} | PDF: {len(r.invoices)} | dopasowane: {r.matched} | "
             f"bez PDF: {r.missing} | PDF bez CSV: {len(r.unmatched_invoices)} | zakładki: {len(self.sheets)}")
        if self.pushed_tabs:
            s += f" | Google Sheets: zapisano {len(self.pushed_tabs)} zakładek"
        if self.nbp_error:
            s += f" | UWAGA: API NBP niedostępne ({self.nbp_error}) – kolumny PLN bez kursu"
        return s


def run_job(
    csv_paths: Iterable[str | Path],
    pdf_sources: Iterable[str | Path],
    out_path: str | Path,
    rates_file: str | Path | None = None,
    use_nbp: bool = True,
    rate_basis: str = "invoice",
    sheet_id: str | None = None,
    credentials: str | Path | None = None,
    json_dump: str | Path | None = None,
) -> JobResult:
    csv_paths = [Path(p) for p in csv_paths]
    if not csv_paths:
        raise ValueError("nie wskazano raportu CSV")
    stats: dict = {}
    transactions = read_reports(csv_paths, stats)
    if not transactions:
        raise ValueError("raport CSV nie zawiera transakcji")
    known = [t.invoice_number for t in transactions if t.invoice_number]
    pdf_paths = iter_pdf_paths(pdf_sources)
    if not pdf_paths:
        log.warning("nie znaleziono żadnego pliku PDF – arkusz powstanie tylko z raportu CSV")
    invoices = parse_pdfs(pdf_paths, known)
    rates = RateProvider(use_nbp=use_nbp, rates_file=rates_file)
    result = merge(transactions, invoices, rates, rate_basis=rate_basis)
    result.csv_duplicates = stats.get("duplicates", 0)
    sheets = build_sheets(result)
    out = write_xlsx(out_path, sheets)
    log.info("zapisano %s", out)
    if json_dump:
        Path(json_dump).parent.mkdir(parents=True, exist_ok=True)
        Path(json_dump).write_text(json.dumps([i.to_dict() for i in invoices], ensure_ascii=False, indent=1), encoding="utf-8")
    pushed: list[str] = []
    if sheet_id:
        from .gsheets import push_sheets

        pushed = push_sheets(sheet_id, sheets, credentials_path=str(credentials) if credentials else None)
        log.info("Google Sheets: zapisano zakładki: %s", ", ".join(pushed))
    nbp_error = None if (rates.nbp_available or not use_nbp) else (rates.last_error or "błąd połączenia")
    return JobResult(xlsx_path=out, result=result, sheets=[s.name for s in sheets], pushed_tabs=pushed, nbp_error=nbp_error)
