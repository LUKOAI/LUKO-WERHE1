"""Amazon FBA inbound constraints for EU fulfilment centres (state: 2026).

Sources: Seller Central help G200141510 (pallet/box requirements), EU FBA rate
cards 2026 (size tiers), Amazon Carrier SOP Pan-EU (Dec 2025). See
docs/AMAZON_ZASADY.md for the full list with confidence levels. Every number
here can be overridden through ``data/planner_params.json`` (key ``amazon``).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..models import Dims

# --- boxes (kartony) -------------------------------------------------------- #
BOX_MAX_SIDE_CM = 63.5          # any side, standard multi-unit boxes
BOX_MAX_WEIGHT_KG = 23.0        # unless a single oversize unit itself is heavier
BOX_HEAVY_LABEL_KG = 15.0       # "Heavy package / Team lift" label required above this
BOX_MIN_DIMS = Dims(15.2, 10.0, 2.5)
BOX_MIN_WEIGHT_KG = 0.15
BOX_TARE_KG = 0.35              # assumed empty carton weight when not measured

# --- pallets (palety) ------------------------------------------------------- #
PALLET_LENGTH_CM = 120.0        # EUR / CHEP 800 x 1200
PALLET_WIDTH_CM = 80.0
PALLET_MAX_HEIGHT_CM = 180.0    # including the pallet itself
PALLET_BASE_HEIGHT_CM = 14.5    # EUR pallet
PALLET_MAX_GROSS_KG = 500.0     # including pallet
PALLET_WEIGHT_KG = 25.0
PALLET_MAX_LOAD_HEIGHT_CM = PALLET_MAX_HEIGHT_CM - PALLET_BASE_HEIGHT_CM

# --- size tiers (klasy rozmiaru), EU rate card 2026 ------------------------- #
DIM_WEIGHT_DIVISOR = 5000.0


@dataclass(frozen=True)
class SizeTier:
    code: str
    name_pl: str
    max_dims: Optional[Dims]           # None = no upper bound (special oversize)
    max_unit_kg: Optional[float]
    max_dim_kg: Optional[float]        # dimensional-weight cap, None when not used
    standard_size: bool                # True = "standard size" (sortable), False = oversize


SIZE_TIERS: list[SizeTier] = [
    SizeTier("light_envelope", "Lekka koperta", Dims(33, 23, 2.5), 0.10, None, True),
    SizeTier("standard_envelope", "Koperta standardowa", Dims(33, 23, 2.5), 0.46, None, True),
    SizeTier("large_envelope", "Duża koperta", Dims(33, 23, 4), 0.96, None, True),
    SizeTier("xl_envelope", "Bardzo duża koperta", Dims(33, 23, 6), 0.96, None, True),
    SizeTier("small_parcel", "Mała paczka", Dims(35, 25, 12), 3.90, 2.10, True),
    SizeTier("standard_parcel", "Paczka standardowa", Dims(45, 34, 26), 11.90, 7.96, True),
    SizeTier("small_oversize", "Mała ponadwymiarowa", Dims(61, 46, 46), 1.76, 25.82, False),
    SizeTier("standard_oversize", "Standardowa ponadwymiarowa", Dims(120, 60, 60), 29.76, 86.4, False),
    SizeTier("large_oversize", "Duża ponadwymiarowa", Dims(150, 60, 60), 31.5, 108.0, False),
    SizeTier("special_oversize", "Specjalna ponadwymiarowa", None, None, None, False),
]
_TIER_BY_CODE = {t.code: t for t in SIZE_TIERS}


def size_tier(dims: Optional[Dims], unit_weight_kg: Optional[float]) -> Optional[SizeTier]:
    """Return the EU size tier for a packaged unit, or None when data is missing."""
    if dims is None:
        return None
    w = unit_weight_kg if unit_weight_kg is not None else 0.0
    dw = dims.dimensional_weight_kg(DIM_WEIGHT_DIVISOR)
    for t in SIZE_TIERS:
        if t.max_dims is None:
            return t
        if not dims.fits_in(t.max_dims):
            continue
        if t.max_unit_kg is not None and w > t.max_unit_kg + 1e-9:
            continue
        if t.max_dim_kg is not None and dw > t.max_dim_kg + 1e-9:
            continue
        return t
    return _TIER_BY_CODE["special_oversize"]


def is_standard_size(dims: Optional[Dims], unit_weight_kg: Optional[float]) -> Optional[bool]:
    """True when the unit is 'standard size' (sortable network), False when oversize, None if unknown."""
    t = size_tier(dims, unit_weight_kg)
    return None if t is None else t.standard_size


# --- validations ------------------------------------------------------------ #
def validate_box(dims: Optional[Dims], weight_kg: Optional[float], single_oversize_unit: bool = False) -> list[str]:
    """Return a list of Polish problem descriptions for a box (empty = OK)."""
    issues: list[str] = []
    if dims is not None:
        if dims.longest > BOX_MAX_SIDE_CM + 1e-9 and not single_oversize_unit:
            issues.append(f"bok kartonu {dims.longest:.1f} cm > {BOX_MAX_SIDE_CM} cm (dozwolone tylko dla pojedynczej sztuki oversize)")
        if not BOX_MIN_DIMS.fits_in(dims):
            issues.append("karton mniejszy niż minimum 15,2 × 10 × 2,5 cm")
    if weight_kg is not None:
        if weight_kg > BOX_MAX_WEIGHT_KG + 1e-9 and not single_oversize_unit:
            issues.append(f"karton {weight_kg:.1f} kg > {BOX_MAX_WEIGHT_KG:.0f} kg")
        elif weight_kg > BOX_HEAVY_LABEL_KG:
            issues.append(f"karton {weight_kg:.1f} kg > {BOX_HEAVY_LABEL_KG:.0f} kg — wymagana etykieta „ciężka paczka”")
    return issues


def validate_pallet(load_height_cm: float, gross_weight_kg: float) -> list[str]:
    issues: list[str] = []
    total_h = load_height_cm + PALLET_BASE_HEIGHT_CM
    if total_h > PALLET_MAX_HEIGHT_CM + 1e-9:
        issues.append(f"wysokość palety {total_h:.0f} cm > {PALLET_MAX_HEIGHT_CM:.0f} cm")
    if gross_weight_kg > PALLET_MAX_GROSS_KG + 1e-9:
        issues.append(f"masa palety {gross_weight_kg:.0f} kg > {PALLET_MAX_GROSS_KG:.0f} kg")
    return issues


def apply_overrides(params: dict) -> None:
    """Override module constants from planner_params.json → {"amazon": {...}}."""
    global BOX_MAX_SIDE_CM, BOX_MAX_WEIGHT_KG, BOX_HEAVY_LABEL_KG, PALLET_MAX_HEIGHT_CM, PALLET_MAX_GROSS_KG
    global PALLET_BASE_HEIGHT_CM, PALLET_WEIGHT_KG, PALLET_MAX_LOAD_HEIGHT_CM, BOX_TARE_KG
    a = (params or {}).get("amazon", {})
    BOX_MAX_SIDE_CM = float(a.get("box_max_side_cm", BOX_MAX_SIDE_CM))
    BOX_MAX_WEIGHT_KG = float(a.get("box_max_weight_kg", BOX_MAX_WEIGHT_KG))
    BOX_HEAVY_LABEL_KG = float(a.get("box_heavy_label_kg", BOX_HEAVY_LABEL_KG))
    BOX_TARE_KG = float(a.get("box_tare_kg", BOX_TARE_KG))
    PALLET_MAX_HEIGHT_CM = float(a.get("pallet_max_height_cm", PALLET_MAX_HEIGHT_CM))
    PALLET_BASE_HEIGHT_CM = float(a.get("pallet_base_height_cm", PALLET_BASE_HEIGHT_CM))
    PALLET_MAX_GROSS_KG = float(a.get("pallet_max_gross_kg", PALLET_MAX_GROSS_KG))
    PALLET_WEIGHT_KG = float(a.get("pallet_weight_kg", PALLET_WEIGHT_KG))
    PALLET_MAX_LOAD_HEIGHT_CM = PALLET_MAX_HEIGHT_CM - PALLET_BASE_HEIGHT_CM
