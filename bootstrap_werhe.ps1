$ErrorActionPreference = "Stop"
Set-Location "C:\Users\user\LUKO-WERHE1"

function W($p,$c){
  $d=Split-Path -Parent $p
  if($d -and -not (Test-Path $d)){ New-Item -ItemType Directory -Path $d | Out-Null }
  [IO.File]::WriteAllText($p,$c,[Text.Encoding]::UTF8)
}

W ".gitignore" @"
.venv/
__pycache__/
*.pyc
dist/
build/
*.spec
output/
"@

W "requirements.txt" @"
customtkinter==5.2.2
reportlab==4.2.2
Pillow==10.4.0
pyinstaller==6.10.0
"@

W "README.md" @"
# WERHE/WERKON DEMO (bez API)

To jest wersja demonstracyjna:
- GUI desktop
- generowanie przykÅ‚adowego PDF
- brak poÅ‚Ä…czeÅ„ do Apilo (symulacja)

## Uruchomienie
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
"@

W "build_exe.bat" @"
@echo off
setlocal
if not exist .venv python -m venv .venv
call .venv\Scripts\activate
pip install -U pip
pip install -r requirements.txt
pyinstaller --noconfirm --clean --onefile --windowed --name WerheDemo main.py
echo GOTOWE: dist\WerheDemo.exe
pause
"@

W "main.py" @"
import customtkinter as ctk
from pathlib import Path
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

def make_demo_pdf():
    out = Path(""output"")
    out.mkdir(exist_ok=True)
    p = out / f""demo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf""
    c = canvas.Canvas(str(p), pagesize=A4)
    c.setFont(""Helvetica-Bold"", 16)
    c.drawString(72, 800, ""WERHE/WERKON - DEMO dokumentu"")
    c.setFont(""Helvetica"", 11)
    c.drawString(72, 770, ""To jest symulacja bez dostÄ™pu do Apilo i trackingu."")
    c.drawString(72, 750, ""Data: "" + datetime.now().strftime(""%Y-%m-%d %H:%M:%S""))
    c.drawString(72, 730, ""ZamÃ³wienie: DEMO-0001"")
    c.drawString(72, 710, ""Kraj: USA, Kurier: UPS"")
    c.drawString(72, 690, ""Status: Delivered (symulacja)"")
    c.save()
    return p

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(""WERHE/WERKON DEMO"")
        self.geometry(""760x420"")
        ctk.set_appearance_mode(""light"")
        ctk.set_default_color_theme(""blue"")

        ctk.CTkLabel(self, text=""Demo bez API (do prezentacji przez TeamViewer)"", font=(""Arial"", 18, ""bold"")).pack(pady=16)
        ctk.CTkButton(self, text=""Wygeneruj przykÅ‚adowy PDF"", command=self.run_demo).pack(pady=10)
        self.log = ctk.CTkTextbox(self, width=700, height=260)
        self.log.pack(pady=10)

    def run_demo(self):
        p = make_demo_pdf()
        self.log.insert(""end"", f""OK: wygenerowano {p}`n"")
        self.log.see(""end"")

if __name__ == ""__main__"":
    App().mainloop()
"@

git add .
if((git status --porcelain).Length -gt 0){
  git commit -m "Add demo-only desktop app (no API) for TeamViewer onboarding"
  git push -u origin work
  Write-Host "DONE: commit + push"
}else{
  Write-Host "Brak zmian do commit."
}
