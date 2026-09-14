"""Aktualizacja programu Auto_Potwierdzenia do najnowszej wersji z GitHub.

Uruchom w folderze programu (PowerShell):
    .\\.venv\\Scripts\\python.exe update.py

Pobiera WSZYSTKIE pliki programu z galezi produkcyjnej. Nie rusza:
config.json (Twoje ustawienia i tokeny), browser_profiles (logowania), logs, wynikow.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

OWNER, REPO = "LUKOAI", "LUKO-WERHE1"
BRANCH = "claude/desktop-automation-tool-PhjMR"
RAW = f"https://raw.githubusercontent.com/{OWNER}/{REPO}/{BRANCH}/"
API = f"https://api.github.com/repos/{OWNER}/{REPO}"

# Pliki nigdy nie nadpisywane (lokalne dane uzytkownika)
NEVER = {"config.json"}
# Co pobieramy: kod aplikacji + pliki pomocnicze
WANTED_PREFIXES = ("app/",)
WANTED_ROOT = {
    "main.py", "update.py", "requirements.txt", "config.example.json",
    "INSTRUKCJA.md", "INSTRUKCJA.pdf", "Auto_Potwierdzenia.bat", "README.md",
}
# Awaryjna lista, gdyby API GitHub nie odpowiedzialo
FALLBACK = [
    "main.py", "update.py", "requirements.txt", "config.example.json",
    "INSTRUKCJA.md", "INSTRUKCJA.pdf", "Auto_Potwierdzenia.bat",
    "app/__init__.py", "app/amazon_capture.py", "app/apilo_auth.py",
    "app/apilo_client.py", "app/apilo_panel_capture.py", "app/browser_session.py",
    "app/config.py", "app/filtering.py", "app/gui.py", "app/logging_setup.py",
    "app/models.py", "app/pdf_generator.py", "app/pipeline.py",
    "app/summary_export.py", "app/tracking_capture.py",
]


def _get(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Auto_Potwierdzenia-updater"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _list_files() -> list[str]:
    """Lista plikow galezi z API GitHub; przy bledzie — lista awaryjna."""
    try:
        branch = json.loads(_get(f"{API}/branches/{BRANCH}"))
        tree_sha = branch["commit"]["commit"]["tree"]["sha"]
        tree = json.loads(_get(f"{API}/git/trees/{tree_sha}?recursive=1"))
        paths = [e["path"] for e in tree.get("tree", []) if e.get("type") == "blob"]
        files = [p for p in paths
                 if (p.startswith(WANTED_PREFIXES) and p.endswith(".py")) or p in WANTED_ROOT]
        if files:
            return sorted(files)
    except Exception as exc:  # noqa: BLE001
        print(f"  (API GitHub niedostepne: {exc} - uzywam listy awaryjnej)")
    return FALLBACK


def main() -> int:
    root = Path(__file__).resolve().parent
    if not (root / "app").is_dir():
        print("BLAD: uruchom update.py w folderze programu (tam gdzie jest folder 'app').")
        return 2

    files = _list_files()
    changed, same, failed = [], [], []
    for rel in files:
        if rel in NEVER:
            continue
        target = root / rel
        try:
            data = _get(RAW + rel)
        except Exception as exc:  # noqa: BLE001
            failed.append(f"{rel}: {exc}")
            continue
        old = target.read_bytes() if target.exists() else None
        if old == data:
            same.append(rel)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        changed.append(rel)

    print(f"Zaktualizowano plikow: {len(changed)}")
    for rel in changed:
        print(f"  + {rel}")
    print(f"Bez zmian: {len(same)}")
    if failed:
        print(f"NIE UDALO SIE pobrac ({len(failed)}):")
        for f in failed:
            print(f"  ! {f}")
        return 1
    print("OK - program aktualny. Uruchom go ponownie.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
