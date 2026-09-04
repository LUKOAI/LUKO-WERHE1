"""Kursy walut do przeliczenia na PLN.

Zasada (art. 31a ustawy o VAT): kurs średni NBP z ostatniego dnia roboczego
poprzedzającego dzień powstania obowiązku podatkowego / wystawienia faktury.
Źródła w kolejności: plik kursów użytkownika -> API NBP (tabela A) -> kurs z CSV
Amazon ("Invoice Level Exchange Rate", tylko gdy waluta faktury = PLN).
"""
from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

log = logging.getLogger(__name__)

NBP_URL = "https://api.nbp.pl/api/exchangerates/rates/a/{cur}/{start}/{end}/?format=json"
PER_100 = {"HUF", "JPY", "ISK", "KRW", "CLP"}


@dataclass(frozen=True)
class RateInfo:
    rate: float            # PLN za 1 jednostkę waluty
    rate_date: date        # data publikacji tabeli
    source: str            # np. "NBP 166/A/NBP/2026", "plik kursów", "Amazon (CSV)"


def _parse_any_date(value: str) -> date | None:
    """RRRR-MM-DD / DD.MM.RRRR / DD/MM/RRRR / DD-MM-RRRR -> date."""
    import re

    v = (value or "").strip()
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", v)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.match(r"^(\d{1,2})[./-](\d{1,2})[./-](\d{4})$", v)
    if m:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    return None


class RateProvider:
    def __init__(
        self,
        use_nbp: bool = True,
        rates_file: str | Path | None = None,
        timeout: float = 15.0,
        max_failures: int = 3,
        session=None,
    ) -> None:
        self.use_nbp = use_nbp
        self.timeout = timeout
        self.max_failures = max_failures
        self.failures = 0
        self.last_error: str | None = None
        self._session = session
        self._cache: dict[tuple[str, date], RateInfo | None] = {}
        self.manual: dict[str, list[tuple[date, float]]] = {}
        if rates_file:
            self.load_rates_file(rates_file)

    # ------------------------------------------------------------------ plik
    def load_rates_file(self, path: str | Path) -> None:
        """CSV: waluta,data,kurs (nagłówek PL lub EN; separator , lub ;).

        `data` = data publikacji kursu (tabeli NBP). Do faktury z dnia D brany
        jest ostatni kurs z datą < D.
        """
        text = Path(path).read_text(encoding="utf-8-sig")
        sample = text[:2000]
        delim = ";" if sample.count(";") > sample.count(",") else ","
        reader = csv.DictReader(text.splitlines(), delimiter=delim)
        cols = {c.strip().lower(): c for c in (reader.fieldnames or [])}
        c_cur = cols.get("waluta") or cols.get("currency") or cols.get("kod")
        c_date = cols.get("data") or cols.get("date") or cols.get("effectivedate")
        c_rate = cols.get("kurs") or cols.get("rate") or cols.get("mid")
        if not (c_cur and c_date and c_rate):
            raise ValueError(f"plik kursów {path}: wymagane kolumny waluta,data,kurs (są: {list(cols)})")
        n, skipped = 0, []
        for row in reader:
            try:
                cur = (row[c_cur] or "").strip().upper()
                d = _parse_any_date((row[c_date] or "").strip())
                rate = float((row[c_rate] or "").strip().replace(" ", "").replace(",", "."))
            except (ValueError, KeyError, TypeError):
                d, rate, cur = None, 0.0, ""
            if cur and d and rate > 0:
                self.manual.setdefault(cur, []).append((d, rate))
                n += 1
            elif any((v or "").strip() for v in row.values()):
                skipped.append(row)
        for lst in self.manual.values():
            lst.sort()
        if skipped:
            log.warning("plik kursów %s: pominięto %d wierszy (zły format daty/kursu), np. %s", path, len(skipped), skipped[0])
        if n == 0:
            raise ValueError(f"plik kursów {path}: nie wczytano żadnego kursu (format: waluta;data;kurs, data RRRR-MM-DD lub DD.MM.RRRR)")
        log.info("plik kursów %s: %d kursów", path, n)

    def _from_manual(self, cur: str, ref_date: date) -> RateInfo | None:
        best = None
        for d, rate in self.manual.get(cur, []):
            if d < ref_date:
                best = (d, rate)
            else:
                break
        if best:
            return RateInfo(best[1], best[0], "plik kursów")
        return None

    # ------------------------------------------------------------------- NBP
    def _from_nbp(self, cur: str, ref_date: date) -> RateInfo | None:
        if not self.use_nbp or self.failures >= self.max_failures:
            return None
        import requests  # import lokalny

        sess = self._session or requests
        start = ref_date - timedelta(days=12)
        end = ref_date - timedelta(days=1)
        url = NBP_URL.format(cur=cur.lower(), start=start.isoformat(), end=end.isoformat())
        try:
            resp = sess.get(url, timeout=self.timeout, headers={"Accept": "application/json"})
        except Exception as exc:  # noqa: BLE001
            self.failures += 1
            self.last_error = f"{type(exc).__name__}: {exc}"
            log.warning("NBP niedostępne (%s): %s", url, self.last_error)
            return None
        if resp.status_code == 404:
            log.warning("NBP: brak kursu %s w zakresie %s..%s", cur, start, end)
            return None
        if resp.status_code != 200:
            self.failures += 1
            self.last_error = f"HTTP {resp.status_code}"
            log.warning("NBP HTTP %s dla %s", resp.status_code, url)
            return None
        try:
            data = resp.json()
            rates = data.get("rates") or []
            last = rates[-1]
            mid = float(last["mid"])
            if cur in PER_100:
                mid /= 100.0
            return RateInfo(mid, date.fromisoformat(last["effectiveDate"]), f"NBP {last.get('no', '')}".strip())
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            self.failures += 1
            self.last_error = f"nieoczekiwana odpowiedź NBP: {exc}"
            return None

    # ---------------------------------------------------------------- public
    def get(self, currency: str, ref_date: date | None) -> RateInfo | None:
        cur = (currency or "").upper()
        if not cur or ref_date is None:
            return None
        if cur == "PLN":
            return RateInfo(1.0, ref_date, "PLN")
        key = (cur, ref_date)
        if key in self._cache:
            return self._cache[key]
        failures_before = self.failures
        info = self._from_manual(cur, ref_date) or self._from_nbp(cur, ref_date)
        # błąd transportowy nie jest odpowiedzią – nie zapamiętujemy None
        if info is not None or self.failures == failures_before:
            self._cache[key] = info
        return info

    @property
    def nbp_available(self) -> bool:
        return self.use_nbp and self.failures < self.max_failures
