@echo off
setlocal

echo [1/5] Tworzenie virtualenv (jesli brak)...
if not exist .venv (
  python -m venv .venv
)

echo [2/5] Aktywacja virtualenv...
call .venv\Scripts\activate

echo [3/5] Instalacja zaleznosci...
pip install --upgrade pip
pip install -r requirements.txt

echo [4/5] Instalacja przegladarki Playwright (Chromium)...
python -m playwright install chromium

echo [5/5] Budowanie pliku EXE...
pyinstaller --noconfirm --clean --onefile --windowed --name WerhePdfTool main.py

echo GOTOWE. Sprawdz folder dist\WerhePdfTool.exe
pause
