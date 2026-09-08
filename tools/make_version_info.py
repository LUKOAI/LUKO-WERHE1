"""Plik VERSIONINFO dla PyInstaller (--version-file): właściwości pliku .exe w Windows
(Szczegóły: nazwa produktu, wersja, firma, prawa autorskie, kontakt).

Użycie: python tools/make_version_info.py WYJSCIE.txt NAZWA.exe [opis]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from amazon_vat_merger import APP_NAME, AUTHOR, COPYRIGHT_YEAR, SUPPORT_EMAIL, __version__  # noqa: E402

DESCRIPTION = f"{APP_NAME} – faktury Amazon do arkusza"


def version_tuple(version: str) -> tuple[int, int, int, int]:
    parts = [int(p) for p in version.split(".") if p.isdigit()]
    return tuple((parts + [0, 0, 0, 0])[:4])  # type: ignore[return-value]


def render(original_filename: str, description: str = DESCRIPTION) -> str:
    vt = version_tuple(__version__)
    internal = Path(original_filename).stem
    strings = [
        ("CompanyName", AUTHOR),
        ("FileDescription", description),
        ("FileVersion", __version__),
        ("InternalName", internal),
        ("LegalCopyright", f"© {COPYRIGHT_YEAR} {AUTHOR} · {SUPPORT_EMAIL}"),
        ("OriginalFilename", original_filename),
        ("ProductName", APP_NAME),
        ("ProductVersion", __version__),
        ("Comments", f"pomoc i awarie: {SUPPORT_EMAIL}"),
    ]
    body = ",\n".join(f"        StringStruct({k!r}, {v!r})" for k, v in strings)
    return (
        "VSVersionInfo(\n"
        "  ffi=FixedFileInfo(\n"
        f"    filevers={vt},\n"
        f"    prodvers={vt},\n"
        "    mask=0x3f,\n"
        "    flags=0x0,\n"
        "    OS=0x40004,\n"
        "    fileType=0x1,\n"
        "    subtype=0x0,\n"
        "    date=(0, 0)\n"
        "  ),\n"
        "  kids=[\n"
        "    StringFileInfo([\n"
        "      StringTable('041504B0', [\n"
        f"{body}\n"
        "      ])\n"
        "    ]),\n"
        "    VarFileInfo([VarStruct('Translation', [1045, 1200])])\n"
        "  ]\n"
        ")\n"
    )


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    out = Path(sys.argv[1])
    out.write_text(render(sys.argv[2], *sys.argv[3:4]), encoding="utf-8")
    print(f"zapisano {out} ({__version__})")
