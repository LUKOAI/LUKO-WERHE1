from datetime import date
from pathlib import Path

from openpyxl import Workbook

from fbaplan.catalog.store import Resolver, load_aliases, load_products
from fbaplan.history.store import compute_stats, import_files, load_history_lines
from fbaplan.models import Alias, Product

ROOT = Path(__file__).resolve().parent.parent


def _xlsx(path: Path):
    wb = Workbook()
    ws = wb.active
    # layout of the client's xlsx exports: col A = header / shipment id, col B = product, col C = qty
    ws.append(["FBA (03.06.26, 10:15) - XPO1", None, None])
    ws.append(["FBA15ABCDEFG | 9ZZZ99ZZ", "WERHE Świder glebowy do wiertarki 80 mm Ø, 600 mm długości", 26])
    ws.append([None, "WERHE Wiertło do ziemi 100 mm z SDS Plus", 10])
    ws.append([None, None, None])
    ws.append(["FBA (03.06.26, 10:20) - WRO5", None, None])
    ws.append(["FBA15ABCDEFH | 9ZZZ99ZY", "WERHE Adapter do świdra SDS PLUS", 40])
    wb.save(str(path))


def test_import_resolves_and_stats(tmp_path: Path):
    src = tmp_path / "raw"
    src.mkdir()
    _xlsx(src / "2026-06.xlsx")
    products = {
        "1Wo80x600": Product("1Wo80x600", "Świder Ogrodowy 80X600", "auger"),
        "1ZWG100dp": Product("1ZWG100dp", "Świder do Gleby 100D SDS PLUS", "auger"),
        "4APlus": Product("4APlus", "Adapter do świdra SDS PLUS", "adapter"),
    }
    aliases = [Alias("WERHE Świder glebowy do wiertarki 80 mm Ø, 600 mm długości", "1Wo80x600", "WERHE", 0.9, "test"),
               Alias("WERHE Wiertło do ziemi 100 mm z SDS Plus", "1ZWG100dp", "WERHE", 0.9, "test")]
    out = tmp_path / "history"
    n, m, unresolved = import_files(list(src.iterdir()), Resolver(products, aliases), out)
    assert (n, m, unresolved) == (2, 3, 0)  # adapter resolved through catalog name match
    lines = load_history_lines(out)
    assert {l.sku for l in lines} == {"1Wo80x600", "1ZWG100dp", "4APlus"}
    assert all(l.when == date(2026, 6, 3) for l in lines)
    st = compute_stats(lines, as_of=date(2026, 9, 1))
    assert st.by_sku["1Wo80x600"].units_12m == 26 and st.by_sku["1Wo80x600"].fc_counter["XPO1"] == 1
    assert st.affinity("1Wo80x600", "1ZWG100dp") > 1.0
    assert st.affinity("1Wo80x600", "4APlus") == 0.0


def test_repo_catalog_and_aliases_consistent():
    products = load_products(ROOT / "data" / "products.csv")
    aliases = load_aliases(ROOT / "data" / "product_aliases.csv")
    assert len(products) >= 400 and len(aliases) >= 1300
    missing = {a.sku for a in aliases} - set(products)
    # only placeholder codes ending with '?' may lack a product
    assert all(s.endswith("?") for s in missing), sorted(missing)[:10]
    r = Resolver(products, aliases)
    a = next(a for a in aliases if a.sku == "2WB14x600p")
    sku, brand, conf, how = r.resolve(a.name)
    assert sku == "2WB14x600p" and how == "alias"
    # unseen title of a known product resolves through the feature key
    sku2, _, _, how2 = r.resolve("WERKON wiertło do betonu SDS Plus 14 x 600 mm, udarowe")
    assert sku2 == "2WB14x600p" and how2 == "fkey"
