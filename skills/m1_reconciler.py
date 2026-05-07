from __future__ import annotations

from dataclasses import dataclass
from datetime import date


VALID_ADJUSTMENT_TYPES: frozenset[str] = frozenset({
    "meals_50pct",
    "fines",
    "officer_life_insurance",
    "federal_income_tax",
    "other_nondeductible",
})

_DEFAULT_CATEGORY_MAP: dict[str, str] = {
    "meals": "meals_50pct",
    "entertainment": "meals_50pct",
    "meals_and_entertainment": "meals_50pct",
    "fines": "fines",
    "penalties": "fines",
    "officer_life_insurance": "officer_life_insurance",
    "life_insurance": "officer_life_insurance",
    "federal_income_tax": "federal_income_tax",
}

_ZERO_YEAR_STATE: dict[str, float] = {
    "meals_total": 0.0,
    "fines_total": 0.0,
    "officer_life_insurance_total": 0.0,
    "other_nondeductible_total": 0.0,
    "gaap_depreciation_total": 0.0,
    "macrs_depreciation_total": 0.0,
    "federal_income_tax_total": 0.0,
}


@dataclass
class M1Draft:
    year: int
    entity_type: str
    line1_book_income: float
    line2_federal_tax: float
    line5a_meals_disallowed: float
    line5b_depreciation_diff: float
    line7_other_nondeductible: float
    line8_taxable_income: float
    formatted: str


class M1Reconciler:
    _ADJUSTMENT_FIELD: dict[str, str] = {
        "meals_50pct": "meals_total",
        "fines": "fines_total",
        "officer_life_insurance": "officer_life_insurance_total",
        "federal_income_tax": "federal_income_tax_total",
        "other_nondeductible": "other_nondeductible_total",
    }

    def __init__(self, memory_manager) -> None:
        self.memory = memory_manager
        self._state: dict[str, dict[str, float]] = self.memory.load_m1_state()
        self._custom_map: dict[str, str] = self.memory.load_m1_category_map()

    def _year_key(self, year: int | None) -> str:
        return str(year if year is not None else date.today().year)

    def _get_year_state(self, year_key: str) -> dict[str, float]:
        if year_key not in self._state:
            self._state[year_key] = dict(_ZERO_YEAR_STATE)
        return self._state[year_key]

    def add_category_mapping(self, category: str, adjustment_type: str) -> None:
        if adjustment_type not in VALID_ADJUSTMENT_TYPES:
            raise ValueError(
                f"Invalid adjustment_type {adjustment_type!r}. "
                f"Valid values: {sorted(VALID_ADJUSTMENT_TYPES)}"
            )
        self._custom_map[category.strip().lower()] = adjustment_type
        self.memory.save_m1_category_map(dict(self._custom_map))

    def get_ytd_summary(self, year: int | None = None) -> dict[str, float]:
        yk = self._year_key(year)
        if yk not in self._state:
            return dict(_ZERO_YEAR_STATE)
        return dict(self._state[yk])

    def record_transaction(
        self, amount: float, category: str, year: int | None = None
    ) -> str | None:
        key = category.strip().lower()
        adj_type = self._custom_map.get(key)
        if adj_type is None:
            adj_type = _DEFAULT_CATEGORY_MAP.get(key)
        if adj_type is None:
            return None
        yk = self._year_key(year)
        ys = self._get_year_state(yk)
        field = self._ADJUSTMENT_FIELD[adj_type]
        ys[field] = round(ys[field] + amount, 2)
        self.memory.save_m1_state(self._state)
        return adj_type

    def record_depreciation_difference(
        self, gaap_amount: float, macrs_amount: float, year: int | None = None
    ) -> None:
        yk = self._year_key(year)
        ys = self._get_year_state(yk)
        ys["gaap_depreciation_total"] = round(ys["gaap_depreciation_total"] + gaap_amount, 2)
        ys["macrs_depreciation_total"] = round(ys["macrs_depreciation_total"] + macrs_amount, 2)
        self.memory.save_m1_state(self._state)
