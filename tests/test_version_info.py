import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location("make_version_info", ROOT / "tools" / "make_version_info.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["make_version_info"] = mod
    spec.loader.exec_module(mod)
    return mod


class _Node:
    def __init__(self, *a, **k):
        self.a, self.k = a, k


def test_version_info_file_is_valid_and_carries_contact():
    from amazon_vat_merger import SUPPORT_EMAIL, __version__, about_line
    mod = _load()
    text = mod.render("LUKO-AmaFakt.exe")
    ns = {n: _Node for n in ("VSVersionInfo", "FixedFileInfo", "StringFileInfo", "StringTable", "StringStruct", "VarFileInfo", "VarStruct")}
    info = eval(text, ns)  # noqa: S307 – taki sam parser (eval) stosuje PyInstaller
    assert info.k["ffi"].k["filevers"] == mod.version_tuple(__version__) and len(info.k["ffi"].k["filevers"]) == 4
    assert f"StringStruct('FileVersion', '{__version__}')" in text and SUPPORT_EMAIL in text
    assert "OriginalFilename', 'LUKO-AmaFakt.exe'" in text and "InternalName', 'LUKO-AmaFakt'" in text
    assert __version__ in about_line() and SUPPORT_EMAIL in about_line()
