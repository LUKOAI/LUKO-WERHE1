#!/usr/bin/env bash
# Demo (macOS / Linux): raport Amazon (CSV) + faktury (PDF) -> arkusz xlsx (+ opcjonalnie Google Sheets)
#
#   ./demo.sh                  -> dane/*.csv + dane/faktury/  ->  output/amazon_vat_<data>.xlsx
#   ./demo.sh <ID_ARKUSZA>     -> dodatkowo nadpisuje zakładki w arkuszu Google
#                                 (wymaga credentials/service_account.json udostępnionego do arkusza)
#   NO_OPEN=1 ./demo.sh        -> nie otwieraj pliku po zakończeniu
set -euo pipefail
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"

if [ ! -d .venv ]; then
  echo ">> tworzę środowisko .venv"
  "$PY" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -r requirements-merger.txt

shopt -s nullglob
CSVS=()
for f in dane/*.csv; do
  case "$(basename "$f")" in kursy.csv|kursy_*.csv) ;; *) CSVS+=("$f");; esac
done
if [ ${#CSVS[@]} -eq 0 ]; then
  echo "!! brak raportu: wrzuć plik CSV (Amazon VAT Transactions Report) do katalogu dane/"; exit 1
fi
if [ ! -d dane/faktury ]; then
  echo "!! brak katalogu dane/faktury z fakturami PDF"; exit 1
fi

ARGS=()
for f in "${CSVS[@]}"; do ARGS+=(--csv "$f"); done
ARGS+=(--pdf dane/faktury)
[ -f dane/kursy.csv ] && ARGS+=(--rates-file dane/kursy.csv)

OUT="output/amazon_vat_$(date +%Y%m%d_%H%M).xlsx"
ARGS+=(--out "$OUT" --json "output/faktury.json")

SHEET_ID="${1:-${AMAZON_VAT_SHEET_ID:-}}"
if [ -n "$SHEET_ID" ]; then
  if [ ! -f credentials/service_account.json ]; then
    echo "!! brak credentials/service_account.json – pomijam wysyłkę do Google Sheets"
  else
    ARGS+=(--sheet-id "$SHEET_ID" --credentials credentials/service_account.json)
  fi
fi

echo ">> python -m amazon_vat_merger ${ARGS[*]}"
python -m amazon_vat_merger "${ARGS[@]}"

if [ -z "${NO_OPEN:-}" ]; then
  if command -v open >/dev/null 2>&1; then open "$OUT"; elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$OUT" || true; fi
fi
