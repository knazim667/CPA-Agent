"""
Perpetual inventory engine for LLC businesses selling physical goods.

Tracks individual purchase lots so COGS and balance-sheet value can be computed
under FIFO, LIFO, or Weighted Average Cost (WAC) at any point in time.

IRS / GAAP rules encoded here:
  - Landed cost (IRC §471): inventory cost includes freight, duties, and insurance
  - Two-entry sale rule: every sale creates a revenue entry AND a COGS entry
  - Lower of Cost or Market (LCM): ASC 330 — write down if market < book cost
  - LIFO reserve: FIFO value − LIFO value, required balance-sheet disclosure
  - LIFO is not permitted under IFRS (only GAAP)
  - Election: inventory method is chosen on the first tax return and requires IRS
    approval (Form 970) to change — ask the business owner on setup
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Any


# ── Lot dataclass ─────────────────────────────────────────────────────────────

@dataclass
class InventoryLot:
    lot_id: str
    purchase_date: str          # YYYY-MM-DD, used for FIFO/LIFO ordering
    units: float                # original units purchased in this lot
    unit_landed_cost: float     # per-unit landed cost (base + freight + duties + ins)
    remaining_units: float      # decremented as units are sold


# ── Engine ────────────────────────────────────────────────────────────────────

class InventoryEngine:
    """
    Perpetual inventory tracking with FIFO, LIFO, and WAC costing.

    Perpetual method: every purchase and sale updates lot balances immediately,
    giving real-time COGS and on-hand inventory value at any moment.

    Usage:
        engine = InventoryEngine(default_method="fifo")
        engine.add_purchase(100, unit_cost=50.0, freight=200)
        engine.record_sale(40, sale_price_per_unit=80.0)
        print(engine.get_summary())
    """

    VALID_METHODS = ("fifo", "lifo", "wac")

    def __init__(self, default_method: str = "fifo") -> None:
        if default_method not in self.VALID_METHODS:
            raise ValueError(f"method must be one of {self.VALID_METHODS}")
        self.default_method = default_method
        self._lots: list[InventoryLot] = []               # oldest → newest
        self._sales_history: list[dict[str, Any]] = []
        self._purchase_history: list[dict[str, Any]] = []
        self._impairments: list[dict[str, Any]] = []

    # ── Public API ─────────────────────────────────────────────────────────────

    def add_purchase(
        self,
        units: float,
        unit_cost: float,
        freight: float = 0.0,
        duties: float = 0.0,
        insurance: float = 0.0,
        purchase_date: str | None = None,
    ) -> dict[str, Any]:
        """
        Record an inventory purchase and compute the fully-landed unit cost.

        Landed cost per unit = (base_cost × units + freight + duties + insurance) / units

        This is required by IRC §471: inventory cost must include all charges
        incidental to acquiring the goods (shipping, customs, insurance).

        Journal entry:
            DR 1200 Inventory    (full landed cost)
            CR 1010 Checking     (full landed cost)
        """
        if units <= 0:
            raise ValueError("units must be positive")

        total_cost = unit_cost * units + freight + duties + insurance
        landed_per_unit = total_cost / units

        lot = InventoryLot(
            lot_id=str(uuid.uuid4())[:8],
            purchase_date=purchase_date or str(date.today()),
            units=units,
            unit_landed_cost=round(landed_per_unit, 6),
            remaining_units=units,
        )
        self._lots.append(lot)

        record = {
            "lot_id": lot.lot_id,
            "purchase_date": lot.purchase_date,
            "units": units,
            "unit_base_cost": round(unit_cost, 2),
            "freight": round(freight, 2),
            "duties": round(duties, 2),
            "insurance": round(insurance, 2),
            "total_landed_cost": round(total_cost, 2),
            "unit_landed_cost": round(landed_per_unit, 4),
            "journal_entry": {
                "debit":  {"account": 1200, "name": "Inventory",        "amount": round(total_cost, 2)},
                "credit": {"account": 1010, "name": "Checking Account", "amount": round(total_cost, 2)},
            },
        }
        self._purchase_history.append(record)
        return record

    def record_sale(
        self,
        units_sold: float,
        sale_price_per_unit: float,
        method: str | None = None,
    ) -> dict[str, Any]:
        """
        Record a sale, charge COGS, and return both required journal entries.

        Two entries are always required (GAAP):
          Entry 1 — Revenue:  DR 1010 Cash / CR 4000 Sales Revenue
          Entry 2 — COGS:     DR 5000 COGS / CR 1200 Inventory

        Raises ValueError if more units are requested than are on hand.
        """
        method = (method or self.default_method).lower()
        if method not in self.VALID_METHODS:
            raise ValueError(f"method must be one of {self.VALID_METHODS}")

        on_hand = self.units_on_hand()
        if units_sold > on_hand:
            raise ValueError(
                f"Cannot sell {units_sold} units — only {on_hand:.2f} on hand"
            )

        if method == "fifo":
            cogs = self._charge_fifo(units_sold)
        elif method == "lifo":
            cogs = self._charge_lifo(units_sold)
        else:
            cogs = self._charge_wac(units_sold)

        revenue = round(units_sold * sale_price_per_unit, 2)
        cogs = round(cogs, 2)
        gross_profit = round(revenue - cogs, 2)

        record = {
            "units_sold": units_sold,
            "method": method,
            "revenue": revenue,
            "cogs": cogs,
            "gross_profit": gross_profit,
            "gross_margin_pct": round(gross_profit / revenue * 100, 1) if revenue else 0.0,
            "journal_entries": [
                {
                    "entry": "Revenue",
                    "debit":  {"account": 1010, "name": "Checking Account", "amount": revenue},
                    "credit": {"account": 4000, "name": "Sales Revenue",    "amount": revenue},
                },
                {
                    "entry": "COGS",
                    "debit":  {"account": 5000, "name": "Cost of Goods Sold", "amount": cogs},
                    "credit": {"account": 1200, "name": "Inventory",          "amount": cogs},
                },
            ],
        }
        self._sales_history.append(record)
        return record

    def check_impairment(
        self,
        item_description: str,
        market_value_total: float,
    ) -> dict[str, Any] | None:
        """
        Apply the Lower of Cost or Market (LCM) rule per ASC 330.

        If total market value of on-hand inventory < recorded book cost,
        write the difference down immediately as an expense.

        Note: GAAP prohibits reversing a write-down if market value recovers.
        IFRS (IAS 2) allows reversal — flag this if the business reports under IFRS.

        Journal entry (write-down only — returns None if no impairment):
            DR 7900 Inventory Write-Down Expense
            CR 1200 Inventory
        """
        book_cost = self.get_inventory_value()
        if market_value_total >= book_cost:
            return None

        write_down = round(book_cost - market_value_total, 2)

        # Reduce each lot's unit cost proportionally so future COGS reflects lower value
        if book_cost > 0:
            reduction_factor = market_value_total / book_cost
            for lot in self._lots:
                if lot.remaining_units > 0:
                    lot.unit_landed_cost = round(lot.unit_landed_cost * reduction_factor, 6)

        record = {
            "item": item_description,
            "book_cost_before_write_down": round(book_cost, 2),
            "market_value": round(market_value_total, 2),
            "write_down_amount": write_down,
            "gaap_note": "ASC 330 — GAAP prohibits reversal if market later recovers",
            "journal_entry": {
                "debit":  {"account": 7900, "name": "Inventory Write-Down Expense", "amount": write_down},
                "credit": {"account": 1200, "name": "Inventory",                     "amount": write_down},
            },
        }
        self._impairments.append(record)
        return record

    def get_inventory_value(self, method: str | None = None) -> float:
        """Return current balance-sheet value of on-hand inventory."""
        method = (method or self.default_method).lower()
        if method == "wac":
            return self._wac_inventory_value()
        # FIFO and LIFO both use actual remaining lot balances (lot state already
        # reflects which units were depleted during sales)
        return round(sum(l.remaining_units * l.unit_landed_cost for l in self._lots), 2)

    def get_cogs_for_period(self, method: str | None = None) -> float:
        """Return total COGS charged for all sales recorded under the given method."""
        method = (method or self.default_method).lower()
        return round(sum(r["cogs"] for r in self._sales_history if r["method"] == method), 2)

    def units_on_hand(self) -> float:
        return round(sum(l.remaining_units for l in self._lots), 6)

    def get_lifo_reserve(self) -> float:
        """
        LIFO reserve = FIFO inventory value − LIFO inventory value.

        Required balance-sheet disclosure when using LIFO (GAAP only).
        A positive reserve is normal in inflationary periods: it means LIFO gives
        a lower inventory figure because the cheapest (oldest) stock remains on the books.

        Computed by replaying all historical sales against fresh lot copies under
        both FIFO and LIFO, then comparing the resulting on-hand values. This gives
        the correct reserve even after partial lot depletion.
        """
        total_sold = sum(r["units_sold"] for r in self._sales_history)
        if total_sold == 0 or not self._lots:
            return 0.0

        def fresh_lots() -> list[InventoryLot]:
            return [
                InventoryLot(
                    lot_id=l.lot_id,
                    purchase_date=l.purchase_date,
                    units=l.units,
                    unit_landed_cost=l.unit_landed_cost,
                    remaining_units=l.units,   # reset to original quantity
                )
                for l in self._lots
            ]

        # Simulate FIFO depletion (oldest first)
        fifo_copy = fresh_lots()
        _deplete_lots(total_sold, fifo_copy)
        fifo_val = sum(l.remaining_units * l.unit_landed_cost for l in fifo_copy)

        # Simulate LIFO depletion (newest first)
        lifo_copy = fresh_lots()
        _deplete_lots(total_sold, list(reversed(lifo_copy)))
        lifo_val = sum(l.remaining_units * l.unit_landed_cost for l in lifo_copy)

        return round(fifo_val - lifo_val, 2)

    def get_summary(self) -> dict[str, Any]:
        """Dashboard-style snapshot of current inventory state."""
        on_hand = self.units_on_hand()
        inv_value = self.get_inventory_value()
        return {
            "units_on_hand": round(on_hand, 2),
            "inventory_value": round(inv_value, 2),
            "default_method": self.default_method,
            "lifo_reserve": self.get_lifo_reserve(),
            "active_lots": len([l for l in self._lots if l.remaining_units > 0]),
            "total_purchases": len(self._purchase_history),
            "total_sales": len(self._sales_history),
            "total_cogs_charged": round(sum(r["cogs"] for r in self._sales_history), 2),
            "impairments_taken": len(self._impairments),
            "total_impairment_amount": round(sum(r["write_down_amount"] for r in self._impairments), 2),
        }

    # ── Private: COGS charging methods ───────────────────────────────────────

    def _charge_fifo(self, units_sold: float) -> float:
        """Deplete oldest lots first (smallest purchase_date index = oldest)."""
        return _deplete_lots(units_sold, self._lots)

    def _charge_lifo(self, units_sold: float) -> float:
        """Deplete newest lots first."""
        return _deplete_lots(units_sold, list(reversed(self._lots)))

    def _charge_wac(self, units_sold: float) -> float:
        """
        Charge COGS at the current weighted average cost per unit.

        WAC recomputes the average after every purchase, so the cost per unit
        smooths out price fluctuations. After computing COGS, deplete lots
        oldest-first to keep remaining_units consistent.
        """
        total_units = self.units_on_hand()
        total_cost = sum(l.remaining_units * l.unit_landed_cost for l in self._lots)
        if total_units == 0:
            return 0.0
        wac = total_cost / total_units
        cogs = units_sold * wac
        # Deplete physical units oldest-first (WAC doesn't care about lot order for cost)
        _deplete_lots(units_sold, self._lots)
        return cogs

    def _wac_inventory_value(self) -> float:
        total_units = self.units_on_hand()
        if total_units == 0:
            return 0.0
        total_cost = sum(l.remaining_units * l.unit_landed_cost for l in self._lots)
        return round(total_cost, 2)   # WAC value = same as sum of lot values


# ── Module-level helpers ──────────────────────────────────────────────────────

def _deplete_lots(units_needed: float, lots: list[InventoryLot]) -> float:
    """
    Consume `units_needed` from `lots` in order, returning total COGS.
    Mutates remaining_units on each lot in place.
    """
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


