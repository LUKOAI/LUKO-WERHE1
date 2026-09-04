@echo off
REM Demo (Windows): raport Amazon (CSV) + faktury (PDF) -> arkusz xlsx (+ opcjonalnie Google Sheets)
REM   demo.bat                 -> dane\*.csv + dane\faktury\  ->  output\amazon_vat_<data>.xlsx
REM   demo.bat <ID_ARKUSZA>    -> dodatkowo nadpisuje zakladki w arkuszu Google
REM                               (wymaga credentials\service_account.json udostepnionego do arkusza)
setlocal EnableDelayedExpansion
cd /d "%~dp0"
chcp 65001 >nul
set PYTHONUTF8=1

if not exist .venv (
  echo ^>^> tworze srodowisko .venv
  python -m venv .venv || (echo !! brak Pythona – zainstaluj Python 3.11+ ze strony python.org & pause & exit /b 1)
)
call .venv\Scripts\activate.bat
pip install -q -r requirements-merger.txt

set ARGS=
set FOUND=0
for %%f in (dane\*.csv) do (
  if /i not "%%~nxf"=="kursy.csv" (
    set ARGS=!ARGS! --csv "%%f"
    set FOUND=1
  )
)
if "%FOUND%"=="0" (echo !! brak raportu: wrzuc plik CSV ^(Amazon VAT Transactions Report^) do katalogu dane\ & pause & exit /b 1)
if not exist dane\faktury (echo !! brak katalogu dane\faktury z fakturami PDF & pause & exit /b 1)
set ARGS=!ARGS! --pdf dane\faktury
if exist dane\kursy.csv set ARGS=!ARGS! --rates-file dane\kursy.csv

for /f "tokens=1-3 delims=.-/ " %%a in ("%date%") do set D=%%c%%b%%a
set T=%time:~0,2%%time:~3,2%
set T=%T: =0%
set OUT=output\amazon_vat_%D%_%T%.xlsx
set ARGS=!ARGS! --out "%OUT%" --json output\faktury.json

set SHEET_ID=%~1
if "%SHEET_ID%"=="" set SHEET_ID=%AMAZON_VAT_SHEET_ID%
if not "%SHEET_ID%"=="" (
  if exist credentials\service_account.json (
    set ARGS=!ARGS! --sheet-id "%SHEET_ID%" --credentials credentials\service_account.json
  ) else (
    echo !! brak credentials\service_account.json – pomijam wysylke do Google Sheets
  )
)

echo ^>^> python -m amazon_vat_merger !ARGS!
python -m amazon_vat_merger !ARGS!
if errorlevel 1 (pause & exit /b 1)
start "" "%OUT%"
endlocal
