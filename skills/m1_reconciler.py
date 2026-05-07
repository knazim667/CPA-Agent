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


def _format_m1(
    year: int,
    entity_type: str,
    l1: float,
    l2: float,
    l5a: float,
    l5b: float,
    l7: float,
    l8: float,
) -> str:
    label = "C-Corp" if entity_type == "c_corp" else "S-Corp"
    title = f"Schedule M-1 Draft ({year} — {label})"
    sep = "=" * len(title)

    def fmt(v: float) -> str:
        if v < 0:
            return f"({abs(v):>11,.2f})"
        return f" {v:>11,.2f}"

    rows = [title, sep]
    rows.append(f"Line 1:  Net income per books:              {fmt(l1)}")
    if entity_type == "c_corp":
        rows.append(f"Line 2:  Federal income tax:                {fmt(l2)}")
    rows.append(f"Line 5a: Meals & entertainment (50% limit): {fmt(l5a)}")
    rows.append(f"Line 5b: Depreciation timing difference:    {fmt(l5b)}")
    rows.append(f"Line 7:  Other non-deductible expenses:     {fmt(l7)}")
    rows.append(f"Line 8:  Taxable income per return:         {fmt(l8)}")
    return "\n".join(rows)


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

    def generate_draft(
        self,
        book_net_income: float,
        entity_type: str = "s_corp",
        year: int | None = None,
    ) -> M1Draft:
        et = entity_type.lower()
        if et not in ("c_corp", "s_corp"):
            raise ValueError(
                f"entity_type must be 'c_corp' or 's_corp', got {entity_type!r}"
            )
        yk = self._year_key(year)
        yr = int(yk)
        ys = self.get_ytd_summary(yr)

        line1 = round(book_net_income, 2)
        line2 = round(ys["federal_income_tax_total"], 2) if et == "c_corp" else 0.0
        line5a = round(ys["meals_total"] * 0.50, 2)
        line5b = round(ys["gaap_depreciation_total"] - ys["macrs_depreciation_total"], 2)
        line7 = round(
            ys["fines_total"]
            + ys["officer_life_insurance_total"]
            + ys["other_nondeductible_total"],
            2,
        )
        line8 = round(line1 + line2 + line5a + line5b + line7, 2)

        return M1Draft(
            year=yr,
            entity_type=et,
            line1_book_income=line1,
            line2_federal_tax=line2,
            line5a_meals_disallowed=line5a,
            line5b_depreciation_diff=line5b,
            line7_other_nondeductible=line7,
            line8_taxable_income=line8,
            formatted=_format_m1(yr, et, line1, line2, line5a, line5b, line7, line8),
        )
