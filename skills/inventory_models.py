"""InventoryLot dataclass and lot-depletion helper for InventoryEngine."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class InventoryLot:
    lot_id: str
    purchase_date: str
    units: float
    unit_landed_cost: float
    remaining_units: float


def deplete_lots(units_needed: float, lots: list[InventoryLot]) -> float:
    """Consume units_needed from lots in order, returning total COGS. Mutates remaining_units."""
    cogs = 0.0
    remaining = units_needed
    for lot in lots:
        if remaining <= 0:
            break
        if lot.remaining_units == 0:
            continue
        take = min(remaining, lot.remaining_units)
        cogs += take * lot.unit_landed_cost
        lot.remaining_units = round(lot.remaining_units - take, 6)
        remaining = round(remaining - take, 6)
    return cogs
