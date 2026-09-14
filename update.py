"""Aktualizacja programu Auto_Potwierdzenia do najnowszej wersji z GitHub.

Uruchom w folderze programu (PowerShell):
    .\\.venv\\Scripts\\python.exe update.py

Pobiera WSZYSTKIE pliki programu z galezi produkcyjnej — z konkretnego commita,
wiec zestaw plikow jest zawsze spojny. Najpierw sciaga wszystko do pamieci,
dopiero potem zapisuje: jesli cokolwiek sie nie pobierze, NIC nie jest zmieniane.

Nie rusza: config.json (ustawienia i tokeny), Auto_Potwierdzenia.bat (sciezka
na tym komputerze), browser_profiles (logowania), logs, wynikow.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

OWNER, REPO = "LUKOAI", "LUKO-WERHE1"
BRANCH = "claude/desktop-automation-tool-PhjMR"
API = f"https://api.github.com/repos/{OWNER}/{REPO}"

# Pliki nigdy nie nadpisywane (lokalne dane / ustawienia tego komputera)
NEVER = {"config.json", "Auto_Potwierdzenia.bat"}
# Co pobieramy: kod aplikacji + pliki pomocnicze
WANTED_PREFIXES = ("app/",)
WANTED_ROOT = {
    "main.py", "update.py", "requirements.txt", "config.example.json",
    "INSTRUKCJA.md", "INSTRUKCJA.pdf", "README.md",
}
# Awaryjna lista, gdyby API GitHub nie odpowiedzialo
FALLBACK = [
    "main.py", "update.py", "requirements.txt", "config.example.json",
    "INSTRUKCJA.md", "INSTRUKCJA.pdf",
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


def _list_files() -> tuple[list[str], str | None]:
    """(lista plikow, SHA commita) z API GitHub; przy bledzie — (lista awaryjna, None)."""
    try:
        branch = json.loads(_get(f"{API}/branches/{BRANCH}"))
        sha = branch["commit"]["sha"]
        tree_sha = branch["commit"]["commit"]["tree"]["sha"]
        tree = json.loads(_get(f"{API}/git/trees/{tree_sha}?recursive=1"))
        paths = [e["path"] for e in tree.get("tree", []) if e.get("type") == "blob"]
        files = [p for p in paths
                 if (p.startswith(WANTED_PREFIXES) and p.endswith(".py")) or p in WANTED_ROOT]
        if files:
            return sorted(files), sha
    except Exception as exc:  # noqa: BLE001
        print(f"  (API GitHub niedostepne: {exc} - uzywam listy awaryjnej)")
    return FALLBACK, None


def main() -> int:
    root = Path(__file__).resolve().parent
    if not (root / "app").is_dir():
        print("BLAD: uruchom update.py w folderze programu (tam gdzie jest folder 'app').")
        return 2

    files, sha = _list_files()
    # Pobieranie po SHA commita = tresc zawsze zgodna z lista plikow
    # (raw po nazwie galezi bywa cache'owane do 5 min -> stare pliki).
    ref = sha or BRANCH
    base = f"https://raw.githubusercontent.com/{OWNER}/{REPO}/{ref}/"
    print(f"Wersja: {sha[:10] if sha else 'galaz ' + BRANCH + ' (moze byc do 5 min stara)'}")

    # FAZA 1: pobierz wszystko do pamieci
    downloaded: dict[str, bytes] = {}
    failed: list[str] = []
    for rel in files:
        if rel in NEVER:
            continue
        try:
            downloaded[rel] = _get(base + rel)
        except Exception as exc:  # noqa: BLE001
            failed.append(f"{rel}: {exc}")
    if failed:
        print(f"NIE UDALO SIE pobrac ({len(failed)}) - NIC nie zmieniono. Sprawdz internet i uruchom ponownie:")
        for f in failed:
            print(f"  ! {f}")
        return 1

    # FAZA 2: zapisz tylko zmienione (przez plik tymczasowy + podmiana)
    changed, same, locked = [], [], []
    for rel, data in downloaded.items():
        target = root / rel
        try:
            if target.exists() and target.read_bytes() == data:
                same.append(rel)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_name(target.name + ".tmp")
            tmp.write_bytes(data)
            os.replace(tmp, target)
            changed.append(rel)
        except OSError as exc:
            locked.append(f"{rel}: {exc} (zamknij ten plik, jesli jest otwarty, i uruchom update.py ponownie)")

    print(f"Zaktualizowano plikow: {len(changed)}")
    for rel in changed:
        print(f"  + {rel}")
    print(f"Bez zmian: {len(same)}")
    if locked:
        print(f"NIE UDALO SIE zapisac ({len(locked)}):")
        for f in locked:
            print(f"  ! {f}")
        return 1
    print("OK - program aktualny. Uruchom go ponownie.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
