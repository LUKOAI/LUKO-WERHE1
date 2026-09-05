"""Cartons and pallets: how much space a plan takes and how much is left.

The model is deliberately simple and transparent for warehouse staff:

* every plan line is split into full master cartons plus (optionally) one
  partial carton; carton dimensions come from the catalog or are estimated
  from unit dimensions;
* a pallet is filled layer by layer with cartons of the same footprint
  (both orientations tried on the 120 x 80 cm deck), layers are stacked up to
  the Amazon height limit and the weight limit is checked;
* utilisation = carton volume / usable pallet volume, plus "how many more
  cartons of footprint X still fit" so the filler recommender can propose
  quantities that close a layer.
"""
from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field
from typing import Iterable, Optional

from ..models import Dims, Product
from ..rules import amazon as A


# --------------------------------------------------------------------------- #
# Cartons
# --------------------------------------------------------------------------- #
@dataclass
class Carton:
    sku: str                       # product sku, or "MIX" for a mixed carton
    contents: dict[str, int]       # sku -> units
    dims: Optional[Dims]
    weight_kg: Optional[float]
    full: bool = True
    estimated: bool = False
    issues: list[str] = field(default_factory=list)

    @property
    def units(self) -> int:
        return sum(self.contents.values())

    @property
    def volume_cm3(self) -> float:
        return self.dims.volume_cm3 if self.dims else 0.0

    def footprint(self) -> Optional[tuple[float, float]]:
        """(long, short) of the two horizontal sides; carton stands on its largest face."""
        if not self.dims:
            return None
        a, b, c = self.dims.sorted()
        return (a, b)

    @property
    def height(self) -> float:
        return self.dims.sorted()[2] if self.dims else 0.0


def estimate_carton_dims(unit: Dims, n: int, wall_cm: float = 0.6) -> Dims:
    """Arrange n identical units in a grid a x b x c minimising the longest side, then volume."""
    n = max(1, n)
    L, W, H = unit.sorted()
    best: Optional[tuple[tuple[float, float, float], tuple[float, float, float]]] = None
    for a in range(1, n + 1):
        for b in range(1, n // a + 2):
            c = math.ceil(n / (a * b))
            if a * b * c < n:
                continue
            for perm in set(itertools.permutations((a, b, c))):
                d = (L * perm[0], W * perm[1], H * perm[2])
                key = (max(d), d[0] * d[1] * d[2])
                if best is None or key < best[0]:
                    best = (key, d)
    assert best is not None
    d = best[1]
    return Dims(d[0] + 2 * wall_cm, d[1] + 2 * wall_cm, d[2] + 2 * wall_cm)


def carton_for(product: Product, units: int) -> Carton:
    """Build one carton with ``units`` of ``product`` (full or partial)."""
    spec = product.carton
    upc = product.units_per_carton
    full = units >= upc
    dims: Optional[Dims] = None
    weight: Optional[float] = None
    estimated = False
    if spec and spec.dims:
        dims = spec.dims
    elif product.unit_dims:
        dims = estimate_carton_dims(product.unit_dims, upc if full else units)
        estimated = True
    if spec and spec.weight_kg is not None and full:
        weight = spec.weight_kg
    elif product.unit_weight_kg is not None:
        weight = units * product.unit_weight_kg + A.BOX_TARE_KG
        estimated = estimated or not (spec and spec.weight_kg is not None)
    elif spec and spec.weight_kg is not None:
        weight = spec.weight_kg * units / upc
        estimated = True
    single_oversize = upc == 1 and product.unit_dims is not None and product.unit_dims.longest > A.BOX_MAX_SIDE_CM
    issues = A.validate_box(dims, weight, single_oversize_unit=single_oversize)
    return Carton(product.sku, {product.sku: units}, dims, weight, full=full, estimated=estimated, issues=issues)


def cartons_for_line(product: Product, qty: int, allow_partial: bool = True) -> list[Carton]:
    upc = product.units_per_carton
    out = [carton_for(product, upc) for _ in range(qty // upc)]
    rem = qty % upc
    if rem:
        if allow_partial:
            out.append(carton_for(product, rem))
        else:
            out.append(carton_for(product, upc))  # rounded up
    return out


# --------------------------------------------------------------------------- #
# Pallets
# --------------------------------------------------------------------------- #
def per_layer_capacity(footprint: tuple[float, float], deck: tuple[float, float] = (A.PALLET_LENGTH_CM, A.PALLET_WIDTH_CM)) -> int:
    """How many cartons with this footprint fit in one layer of the pallet deck (no overhang)."""
    a, b = footprint
    DL, DW = deck
    if a <= 0 or b <= 0:
        return 0
    o1 = math.floor(DL / a + 1e-9) * math.floor(DW / b + 1e-9)
    o2 = math.floor(DL / b + 1e-9) * math.floor(DW / a + 1e-9)
    return max(o1, o2)


@dataclass
class Layer:
    footprint: tuple[float, float]
    height_cm: float
    cartons: list[Carton]
    capacity: int

    @property
    def free_slots(self) -> int:
        return max(0, self.capacity - len(self.cartons))

    @property
    def weight_kg(self) -> float:
        return sum(c.weight_kg or 0.0 for c in self.cartons)


@dataclass
class PalletLoad:
    layers: list[Layer] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)

    @property
    def cartons(self) -> list[Carton]:
        return [c for l in self.layers for c in l.cartons]

    @property
    def units(self) -> int:
        return sum(c.units for c in self.cartons)

    @property
    def load_height_cm(self) -> float:
        return sum(l.height_cm for l in self.layers)

    @property
    def net_weight_kg(self) -> float:
        return sum(l.weight_kg for l in self.layers)

    @property
    def gross_weight_kg(self) -> float:
        return self.net_weight_kg + A.PALLET_WEIGHT_KG

    @property
    def volume_used_cm3(self) -> float:
        return sum(c.volume_cm3 for c in self.cartons)

    @property
    def volume_capacity_cm3(self) -> float:
        return A.PALLET_LENGTH_CM * A.PALLET_WIDTH_CM * A.PALLET_MAX_LOAD_HEIGHT_CM

    @property
    def fill_ratio(self) -> float:
        cap = self.volume_capacity_cm3
        return self.volume_used_cm3 / cap if cap else 0.0

    @property
    def height_ratio(self) -> float:
        return self.load_height_cm / A.PALLET_MAX_LOAD_HEIGHT_CM if A.PALLET_MAX_LOAD_HEIGHT_CM else 0.0

    @property
    def free_height_cm(self) -> float:
        return max(0.0, A.PALLET_MAX_LOAD_HEIGHT_CM - self.load_height_cm)

    @property
    def free_weight_kg(self) -> float:
        return max(0.0, A.PALLET_MAX_GROSS_KG - self.gross_weight_kg)

    def room_for(self, footprint: tuple[float, float], height_cm: float, weight_kg: float = 0.0) -> int:
        """How many more cartons (footprint, height) fit: free slots in matching partial layers + new layers."""
        n = 0
        for l in self.layers:
            if _same_fp(l.footprint, footprint) and abs(l.height_cm - height_cm) < 0.5:
                n += l.free_slots
        cap = per_layer_capacity(footprint)
        if cap and height_cm > 0:
            n += int(self.free_height_cm // height_cm) * cap
        if weight_kg > 0:
            n = min(n, int(self.free_weight_kg // weight_kg))
        return n


def _same_fp(a: tuple[float, float], b: tuple[float, float]) -> bool:
    return abs(a[0] - b[0]) < 0.5 and abs(a[1] - b[1]) < 0.5


@dataclass
class PackResult:
    pallets: list[PalletLoad]
    unplaceable: list[Carton]      # cartons without dimensions (cannot be placed)
    all_cartons: list[Carton]

    @property
    def units(self) -> int:
        return sum(c.units for c in self.all_cartons)

    @property
    def total_volume_cm3(self) -> float:
        return sum(c.volume_cm3 for c in self.all_cartons)

    @property
    def total_weight_kg(self) -> float:
        return sum(c.weight_kg or 0.0 for c in self.all_cartons)

    @property
    def issues(self) -> list[str]:
        out: list[str] = []
        for i, p in enumerate(self.pallets, 1):
            out += [f"paleta {i}: {x}" for x in p.issues]
        for c in self.all_cartons:
            out += [f"karton {c.sku}: {x}" for x in c.issues]
        if self.unplaceable:
            out.append("brak wymiarów kartonu dla: " + ", ".join(sorted({c.sku for c in self.unplaceable})))
        return out


def build_layers(cartons: Iterable[Carton]) -> list[Layer]:
    """Group cartons by (footprint, height) into layers; full layers first, then partial ones."""
    groups: dict[tuple[float, float, float], list[Carton]] = {}
    for c in cartons:
        fp = c.footprint()
        if fp is None:
            continue
        key = (round(fp[0], 1), round(fp[1], 1), round(c.height, 1))
        groups.setdefault(key, []).append(c)
    layers: list[Layer] = []
    for (a, b, h), cs in groups.items():
        cap = per_layer_capacity((a, b))
        if cap == 0:
            # carton wider than the deck: give it its own layer, flagged
            for c in cs:
                c.issues.append(f"karton {a:.0f}×{b:.0f} cm nie mieści się w obrysie palety 120×80 cm")
                layers.append(Layer((a, b), h, [c], 1))
            continue
        cs = sorted(cs, key=lambda c: -(c.weight_kg or 0))
        for i in range(0, len(cs), cap):
            layers.append(Layer((a, b), h, cs[i:i + cap], cap))
    # heaviest / fullest layers at the bottom
    layers.sort(key=lambda l: (-(l.free_slots == 0), -l.weight_kg, -l.height_cm))
    return layers


def pack_pallets(cartons: list[Carton], max_pallets: int = 0) -> PackResult:
    """Distribute cartons over pallets (layers stacked up to the height and weight limits)."""
    placeable = [c for c in cartons if c.dims is not None]
    unplaceable = [c for c in cartons if c.dims is None]
    layers = build_layers(placeable)
    pallets: list[PalletLoad] = []
    cur = PalletLoad()
    for l in layers:
        fits_h = cur.load_height_cm + l.height_cm <= A.PALLET_MAX_LOAD_HEIGHT_CM + 1e-9
        fits_w = cur.gross_weight_kg + l.weight_kg <= A.PALLET_MAX_GROSS_KG + 1e-9
        if cur.layers and not (fits_h and fits_w):
            pallets.append(cur)
            cur = PalletLoad()
        cur.layers.append(l)
    if cur.layers:
        pallets.append(cur)
    for p in pallets:
        p.issues = A.validate_pallet(p.load_height_cm, p.gross_weight_kg)
    if max_pallets and len(pallets) > max_pallets:
        for p in pallets[max_pallets:]:
            p.issues.append("ponad limit palet w planie")
    return PackResult(pallets, unplaceable, cartons)


def plan_cartons(products: dict[str, Product], lines: Iterable[tuple[str, int]], allow_partial: bool = True) -> list[Carton]:
    out: list[Carton] = []
    for sku, qty in lines:
        p = products.get(sku)
        if p is None or qty <= 0:
            continue
        out += cartons_for_line(p, qty, allow_partial=allow_partial)
    return out


def volume_m3(cartons: Iterable[Carton]) -> float:
    return sum(c.volume_cm3 for c in cartons) / 1e6
