# Uruchamia FBA Plan (interfejs www) na Windows.
# Pierwsze uruchomienie tworzy środowisko .venv i instaluje zależności (wymaga Pythona 3.11+ w PATH).
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

if (-not (Test-Path ".venv")) {
    Write-Host "Tworzę środowisko wirtualne (.venv)..."
    python -m venv .venv
}
& ".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
& ".venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt

Write-Host "Start FBA Plan: http://127.0.0.1:8765  (zamknij to okno, aby zatrzymać)"
& ".venv\Scripts\python.exe" -m fbaplan serve --open
