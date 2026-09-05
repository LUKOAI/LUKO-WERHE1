"""Core data model of fbaplan.

All dimensions are centimetres, all weights kilograms. Products describe the
*physical* item (one canonical SKU per physical product); brand variants
(WERHE / WERKON) are separate Amazon listings (merchant SKUs) of the same item.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from datetime import date, datetime
from typing import Any, Optional


# --------------------------------------------------------------------------- #
# Geometry
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Dims:
    length_cm: float
    width_cm: float
    height_cm: float

    def sorted(self) -> tuple[float, float, float]:
        """Dimensions sorted descending (longest first)."""
        return tuple(sorted((self.length_cm, self.width_cm, self.height_cm), reverse=True))  # type: ignore[return-value]

    @property
    def longest(self) -> float:
        return self.sorted()[0]

    @property
    def volume_cm3(self) -> float:
        return self.length_cm * self.width_cm * self.height_cm

    @property
    def girth_cm(self) -> float:
        a, b, c = self.sorted()
        return a + 2 * (b + c)

    def fits_in(self, box: "Dims") -> bool:
        a, b = self.sorted(), box.sorted()
        return all(x <= y + 1e-9 for x, y in zip(a, b))

    def dimensional_weight_kg(self, divisor: float = 5000.0) -> float:
        return self.volume_cm3 / divisor

    def as_tuple(self) -> tuple[float, float, float]:
        return (self.length_cm, self.width_cm, self.height_cm)

    @staticmethod
    def parse(l: Any, w: Any, h: Any) -> Optional["Dims"]:
        try:
            vals = [float(str(v).replace(",", ".")) for v in (l, w, h)]
        except (TypeError, ValueError):
            return None
        if any(v <= 0 for v in vals):
            return None
        return Dims(*vals)


def _f(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(str(v).replace(",", "."))
    except ValueError:
        return None


def _i(v: Any) -> Optional[int]:
    f = _f(v)
    return int(round(f)) if f is not None else None


# --------------------------------------------------------------------------- #
# Catalog
# --------------------------------------------------------------------------- #
@dataclass
class CartonSpec:
    """Master carton (karton zbiorczy) of one product."""

    units_per_carton: int
    dims: Optional[Dims] = None
    weight_kg: Optional[float] = None
    estimated: bool = False  # dims/weight estimated from unit data, not measured


@dataclass
class Product:
    sku: str  # canonical (Apilo) code, e.g. 1WG80x800p
    name: str  # Polish short name
    family: str = ""  # auger, drill_bit, chisel_flat, adapter, ... (see catalog.normalize)
    brands: list[str] = field(default_factory=list)  # e.g. ["WERHE", "WERKON"]
    mskus: dict[str, str] = field(default_factory=dict)  # brand -> Amazon merchant SKU
    unit_dims: Optional[Dims] = None  # packaged unit
    unit_weight_kg: Optional[float] = None
    carton: Optional[CartonSpec] = None
    fc_override: Optional[str] = None  # manual FC assignment
    pack_group: str = ""  # products from different groups are not packed together
    max_qty_per_plan: Optional[int] = None
    active: bool = True
    notes: str = ""

    @property
    def units_per_carton(self) -> int:
        return self.carton.units_per_carton if self.carton and self.carton.units_per_carton > 0 else 1

    def msku_for(self, brand: str = "") -> str:
        if brand and brand in self.mskus:
            return self.mskus[brand]
        if self.mskus:
            return next(iter(self.mskus.values()))
        return self.sku

    # -- CSV (de)serialisation ------------------------------------------------
    CSV_COLUMNS = [
        "sku", "name", "family", "brands", "msku_werhe", "msku_werkon",
        "unit_length_cm", "unit_width_cm", "unit_height_cm", "unit_weight_kg",
        "units_per_carton", "carton_length_cm", "carton_width_cm", "carton_height_cm", "carton_weight_kg",
        "fc_override", "pack_group", "max_qty_per_plan", "active", "notes",
    ]

    def to_row(self) -> dict[str, Any]:
        ud, cd = self.unit_dims, (self.carton.dims if self.carton else None)
        return {
            "sku": self.sku, "name": self.name, "family": self.family,
            "brands": ";".join(self.brands),
            "msku_werhe": self.mskus.get("WERHE", ""), "msku_werkon": self.mskus.get("WERKON", ""),
            "unit_length_cm": ud.length_cm if ud else "", "unit_width_cm": ud.width_cm if ud else "",
            "unit_height_cm": ud.height_cm if ud else "",
            "unit_weight_kg": self.unit_weight_kg if self.unit_weight_kg is not None else "",
            "units_per_carton": self.carton.units_per_carton if self.carton else "",
            "carton_length_cm": cd.length_cm if cd else "", "carton_width_cm": cd.width_cm if cd else "",
            "carton_height_cm": cd.height_cm if cd else "",
            "carton_weight_kg": (self.carton.weight_kg if self.carton and self.carton.weight_kg is not None else ""),
            "fc_override": self.fc_override or "", "pack_group": self.pack_group,
            "max_qty_per_plan": self.max_qty_per_plan if self.max_qty_per_plan is not None else "",
            "active": "1" if self.active else "0", "notes": self.notes,
        }

    @classmethod
    def from_row(cls, r: dict[str, Any]) -> "Product":
        g = lambda k: (r.get(k) or "").strip() if isinstance(r.get(k), str) else r.get(k)
        mskus = {}
        if g("msku_werhe"):
            mskus["WERHE"] = g("msku_werhe")
        if g("msku_werkon"):
            mskus["WERKON"] = g("msku_werkon")
        brands = [b for b in (g("brands") or "").split(";") if b] or list(mskus.keys())
        upc = _i(g("units_per_carton"))
        carton = None
        if upc:
            carton = CartonSpec(
                units_per_carton=upc,
                dims=Dims.parse(g("carton_length_cm"), g("carton_width_cm"), g("carton_height_cm")),
                weight_kg=_f(g("carton_weight_kg")),
            )
        active = str(g("active") or "1").strip().lower() not in ("0", "false", "nie", "no", "n")
        return cls(
            sku=g("sku"), name=g("name") or g("sku"), family=g("family") or "", brands=brands, mskus=mskus,
            unit_dims=Dims.parse(g("unit_length_cm"), g("unit_width_cm"), g("unit_height_cm")),
            unit_weight_kg=_f(g("unit_weight_kg")), carton=carton,
            fc_override=(g("fc_override") or None), pack_group=g("pack_group") or "",
            max_qty_per_plan=_i(g("max_qty_per_plan")), active=active, notes=g("notes") or "",
        )


@dataclass
class Alias:
    name: str
    sku: str
    brand: str = ""
    confidence: float = 1.0
    source: str = ""


# --------------------------------------------------------------------------- #
# History / evidence
# --------------------------------------------------------------------------- #
@dataclass
class HistoryLine:
    """One product line of one historical (or verdict) shipment."""

    sku: str
    fc: str
    when: date
    qty: int
    shipment_id: str = ""
    kind: str = ""  # "pallet" | "parcel" | ""
    source: str = "history"  # history | verdict
    name: str = ""


@dataclass
class StockRow:
    sku: str
    msku: str = ""
    brand: str = ""
    fba_available: int = 0
    fba_inbound: int = 0
    sales_30d: int = 0
    sales_90d: int = 0
    local_stock: Optional[int] = None  # stock in own warehouse, if known

    @property
    def daily_velocity(self) -> float:
        if self.sales_90d:
            return self.sales_90d / 90.0
        return self.sales_30d / 30.0

    @property
    def cover_days(self) -> Optional[float]:
        v = self.daily_velocity
        if v <= 0:
            return None
        return (self.fba_available + self.fba_inbound) / v


# --------------------------------------------------------------------------- #
# Plans
# --------------------------------------------------------------------------- #
@dataclass
class PlanLine:
    sku: str
    qty: int
    brand: str = ""
    msku: str = ""
    note: str = ""
    locked: bool = False  # user does not want the tool to move/remove this line


@dataclass
class Plan:
    plan_id: str
    created_at: str
    mode: str = "pallet"  # "pallet" | "parcel"
    lines: list[PlanLine] = field(default_factory=list)
    target_fc: str = ""  # desired FC; empty = derive from anchor lines
    max_pallets: int = 1
    excluded_skus: list[str] = field(default_factory=list)
    verdicts: dict[str, str] = field(default_factory=dict)  # sku -> FC as decided by Amazon
    verdict_date: str = ""
    status: str = "draft"  # draft | submitted | verdict | closed
    notes: str = ""

    def qty_of(self, sku: str) -> int:
        return sum(l.qty for l in self.lines if l.sku == sku)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=1)

    @classmethod
    def from_json(cls, s: str) -> "Plan":
        d = json.loads(s)
        d["lines"] = [PlanLine(**l) for l in d.get("lines", [])]
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in known})


def new_plan_id(now: Optional[datetime] = None) -> str:
    now = now or datetime.now()
    return now.strftime("P%Y%m%d-%H%M%S")
