"""Perpetual inventory engine: FIFO, LIFO, and WAC costing for LLC businesses.

Landed cost per IRC §471; every sale requires two journal entries (revenue + COGS).
Supports LCM write-downs (ASC 330) and LIFO reserve disclosure.
LIFO is GAAP-only — not permitted under IFRS.
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from skills.inventory_models import InventoryLot, deplete_lots as _deplete_lots


class InventoryEngine:
    """Perpetual inventory tracking with FIFO, LIFO, and WAC costing."""

    VALID_METHODS = ("fifo", "lifo", "wac")

    def __init__(self, default_method: str = "fifo") -> None:
        if default_method not in self.VALID_METHODS:
            raise ValueError(f"method must be one of {self.VALID_METHODS}")
        self.default_method = default_method
        self._lots: list[InventoryLot] = []
        self._sales_history: list[dict[str, Any]] = []
        self._purchase_history: list[dict[str, Any]] = []
        self._impairments: list[dict[str, Any]] = []

    def add_purchase(
        self,
        units: float,
        unit_cost: float,
        freight: float = 0.0,
        duties: float = 0.0,
        insurance: float = 0.0,
        purchase_date: str | None = None,
    ) -> dict[str, Any]:
        """Record a purchase and compute landed unit cost (IRC §471).

        Landed cost = (base_cost × units + freight + duties + insurance) / units.
        Journal: DR 1200 Inventory / CR 1010 Checking.
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
        """Record a sale, charge COGS under the chosen costing method.

        GAAP requires two entries: Revenue (DR Cash / CR Sales) and COGS (DR COGS / CR Inventory).
        Raises ValueError if units_sold exceeds on-hand quantity.
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
        """Apply LCM rule (ASC 330): write down if market value < book cost.

        GAAP prohibits reversal if market value later recovers.
        Returns None if no write-down is needed.
        Journal: DR 7900 Inventory Write-Down Expense / CR 1200 Inventory.
        """
        book_cost = self.get_inventory_value()
        if market_value_total >= book_cost:
            return None

        write_down = round(book_cost - market_value_total, 2)

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
        return round(sum(l.remaining_units * l.unit_landed_cost for l in self._lots), 2)

    def get_cogs_for_period(self, method: str | None = None) -> float:
        """Return total COGS charged for all sales recorded under the given method."""
        method = (method or self.default_method).lower()
        return round(sum(r["cogs"] for r in self._sales_history if r["method"] == method), 2)

    def units_on_hand(self) -> float:
        return round(sum(l.remaining_units for l in self._lots), 6)

    def get_lifo_reserve(self) -> float:
        """LIFO reserve = FIFO inventory value − LIFO inventory value.

        Required balance-sheet disclosure when using LIFO (GAAP only).
        Computed by replaying all historical sales against fresh lot copies.
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
                    remaining_units=l.units,
                )
                for l in self._lots
            ]

        fifo_copy = fresh_lots()
        _deplete_lots(total_sold, fifo_copy)
        fifo_val = sum(l.remaining_units * l.unit_landed_cost for l in fifo_copy)

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

    def _charge_fifo(self, units_sold: float) -> float:
        return _deplete_lots(units_sold, self._lots)

    def _charge_lifo(self, units_sold: float) -> float:
        return _deplete_lots(units_sold, list(reversed(self._lots)))

    def _charge_wac(self, units_sold: float) -> float:
        total_units = self.units_on_hand()
        total_cost = sum(l.remaining_units * l.unit_landed_cost for l in self._lots)
        if total_units == 0:
            return 0.0
        wac = total_cost / total_units
        cogs = units_sold * wac
        _deplete_lots(units_sold, self._lots)
        return cogs

    def _wac_inventory_value(self) -> float:
        total_units = self.units_on_hand()
        if total_units == 0:
            return 0.0
        total_cost = sum(l.remaining_units * l.unit_landed_cost for l in self._lots)
        return round(total_cost, 2)
