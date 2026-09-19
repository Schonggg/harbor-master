"""Convert weight units to kilograms before compare."""

from __future__ import annotations

import re

from harbormaster.models import Charge, Plea

_WEIGHT_FIELDS = {"gross_weight", "gross_weight_kg", "net_weight", "weight"}

# to kilograms
_FACTORS = {
    "KGS": 1.0,
    "KG": 1.0,
    "KILOGRAMS": 1.0,
    "KILOGRAM": 1.0,
    "MT": 1000.0,
    "MTS": 1000.0,
    "TON": 1000.0,
    "TONS": 1000.0,
    "TONNE": 1000.0,
    "TONNES": 1000.0,
    "LBS": 0.45359237,
    "LB": 0.45359237,
    "POUNDS": 0.45359237,
    "POUND": 0.45359237,
}

# Comma-grouped form MUST come first, else `\d+` steals "25" from "25,400".
_NUM_RE = re.compile(
    r"(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*(?P<unit>[A-Za-z.]+)?",
)


def parse_weight_kg(value: str) -> float | None:
    text = value.strip().upper()
    m = _NUM_RE.search(text)
    if not m:
        return None
    num = float(m.group("num").replace(",", ""))
    unit_raw = (m.group("unit") or "KGS").upper().replace(".", "")
    factor = _FACTORS.get(unit_raw)
    if factor is None:
        factor = _FACTORS.get(unit_raw.rstrip("S") + "S") or _FACTORS.get(unit_raw.rstrip("S"))
    if factor is None:
        return None
    return num * factor


class UnitConvertStrategy:
    name = "unit_convert"

    def try_defend(self, charge: Charge) -> Plea:
        if charge.field not in _WEIGHT_FIELDS and "weight" not in charge.field:
            return Plea(strategy=self.name, accepted=False, argument="not a weight field")
        left = parse_weight_kg(charge.left.raw_value)
        right = parse_weight_kg(charge.right.raw_value)
        if left is None or right is None:
            return Plea(
                strategy=self.name,
                accepted=False,
                argument="could not parse weight",
                transformed_left=None if left is None else f"{left:.4f} KG",
                transformed_right=None if right is None else f"{right:.4f} KG",
            )
        # Official spec: tolerance ≤ 1 kg after conversion.
        ok = abs(left - right) <= 1.0
        return Plea(
            strategy=self.name,
            accepted=ok,
            argument=f"kg compare: {left:.3f} vs {right:.3f}",
            transformed_left=f"{left:.4f} KG",
            transformed_right=f"{right:.4f} KG",
            confidence=1.0 if ok else 0.0,
        )
