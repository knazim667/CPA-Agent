"""Report and data-export routes."""
from __future__ import annotations

import csv
import io
import time
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from auth import require_owner_or_bookkeeper
from routes._state import agent, agent_lock
from skills.pdf_exporter import generate_table_pdf

router = APIRouter()


@router.get("/api/report/pl")
def report_pl(
    from_date: str = "", to_date: str = "",
    current_user: dict = Depends(require_owner_or_bookkeeper),
) -> dict:
    with agent_lock:
        profile = agent.memory.get_current_business()
        if not profile.get("google_sheet_id"):
            raise HTTPException(status_code=400, detail="No ledger connected for this business.")
        rows = agent.sheets.read_range(spreadsheet_id=profile["google_sheet_id"], range_name="Ledger!A1:G")
        data_rows = rows[1:] if rows and rows[0][:len(agent.LEDGER_HEADERS)] == agent.LEDGER_HEADERS else rows
        if from_date or to_date:
            data_rows = [
                r for r in data_rows
                if (not from_date or str(r[0]).strip() >= from_date)
                and (not to_date or str(r[0]).strip() <= to_date)
            ]
        income_by_cat: dict = {}
        expense_by_cat: dict = {}
        for row in data_rows:
            if len(row) < 5:
                continue
            amount = agent._safe_float(row[3] if len(row) > 3 else 0)
            category = str(row[2]).strip() if len(row) > 2 else "Uncategorized"
            if str(row[4]).strip().lower() == "income":
                income_by_cat[category] = income_by_cat.get(category, 0.0) + amount
            else:
                expense_by_cat[category] = expense_by_cat.get(category, 0.0) + amount
        income_total = sum(income_by_cat.values())
        expense_total = sum(expense_by_cat.values())
        return {
            "business": profile["business_name"],
            "from_date": from_date or None,
            "to_date": to_date or None,
            "income_by_category": [{"category": k, "total": round(v, 2)} for k, v in sorted(income_by_cat.items())],
            "expense_by_category": [{"category": k, "total": round(v, 2)} for k, v in sorted(expense_by_cat.items())],
            "income_total": round(income_total, 2),
            "expense_total": round(expense_total, 2),
            "net": round(income_total - expense_total, 2),
        }


@router.get("/api/export/csv")
def export_csv(
    from_date: str = "", to_date: str = "",
    current_user: dict = Depends(require_owner_or_bookkeeper),
):
    with agent_lock:
        profile = agent.memory.get_current_business()
        if not profile.get("google_sheet_id"):
            raise HTTPException(status_code=400, detail="No ledger connected.")
        rows = agent.sheets.read_range(spreadsheet_id=profile["google_sheet_id"], range_name="Ledger!A1:G")
        data_rows = rows[1:] if rows and rows[0][:len(agent.LEDGER_HEADERS)] == agent.LEDGER_HEADERS else rows
        if from_date or to_date:
            data_rows = [
                r for r in data_rows
                if (not from_date or str(r[0]).strip() >= from_date)
                and (not to_date or str(r[0]).strip() <= to_date)
            ]
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(agent.LEDGER_HEADERS)
        for row in data_rows:
            writer.writerow(agent._normalize_row(row))
        output.seek(0)
        today = time.strftime("%Y-%m-%d")
        filename = f"{agent.memory.current_business_key}-ledger-{today}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/api/export/ledger/pdf")
def export_ledger_pdf(
    from_date: str = "", to_date: str = "",
    current_user: dict = Depends(require_owner_or_bookkeeper),
):
    with agent_lock:
        profile = agent.memory.get_current_business()
        if not profile.get("google_sheet_id"):
            raise HTTPException(status_code=400, detail="No ledger connected.")
        rows = agent.sheets.read_range(spreadsheet_id=profile["google_sheet_id"], range_name="Ledger!A1:G")
        data_rows = (
            rows[1:] if rows and len(rows[0]) >= len(agent.LEDGER_HEADERS)
            and rows[0][:len(agent.LEDGER_HEADERS)] == agent.LEDGER_HEADERS else rows
        )
        if from_date or to_date:
            data_rows = [
                r for r in data_rows
                if (not from_date or str(r[0]).strip() >= from_date)
                and (not to_date or str(r[0]).strip() <= to_date)
            ]
        norm = [agent._normalize_row(r) for r in data_rows if isinstance(r, list)]
        subtitle = f"{from_date or 'start'} — {to_date or 'today'}" if (from_date or to_date) else ""
        pdf_bytes = generate_table_pdf(
            title="General Ledger", headers=agent.LEDGER_HEADERS, rows=norm,
            business_name=profile.get("business_name", ""), subtitle=subtitle,
        )
    today = time.strftime("%Y-%m-%d")
    filename = f"{agent.memory.current_business_key}-ledger-{today}.pdf"
    return StreamingResponse(
        iter([pdf_bytes]), media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/api/export/pl/pdf")
def export_pl_pdf(
    from_date: str = "", to_date: str = "",
    current_user: dict = Depends(require_owner_or_bookkeeper),
):
    with agent_lock:
        profile = agent.memory.get_current_business()
        if not profile.get("google_sheet_id"):
            raise HTTPException(status_code=400, detail="No ledger connected.")
        rows = agent.sheets.read_range(spreadsheet_id=profile["google_sheet_id"], range_name="Ledger!A1:G")
        data_rows = (
            rows[1:] if rows and len(rows[0]) >= len(agent.LEDGER_HEADERS)
            and rows[0][:len(agent.LEDGER_HEADERS)] == agent.LEDGER_HEADERS else rows
        )
        if from_date or to_date:
            data_rows = [
                r for r in data_rows
                if (not from_date or str(r[0]).strip() >= from_date)
                and (not to_date or str(r[0]).strip() <= to_date)
            ]
        income_rows = [
            [r[2], f"${agent._safe_float(r[3]):.2f}"]
            for r in data_rows if len(r) >= 5 and str(r[4]).strip().lower() == "income"
        ]
        expense_rows = [
            [r[2], f"${agent._safe_float(r[3]):.2f}"]
            for r in data_rows if len(r) >= 5 and str(r[4]).strip().lower() != "income"
        ]
        all_rows = [["INCOME", ""]] + income_rows + [["EXPENSES", ""]] + expense_rows
        subtitle = f"{from_date or 'start'} — {to_date or 'today'}" if (from_date or to_date) else ""
        pdf_bytes = generate_table_pdf(
            title="Profit & Loss", headers=["Category", "Amount"], rows=all_rows,
            business_name=profile.get("business_name", ""), subtitle=subtitle,
        )
    today = time.strftime("%Y-%m-%d")
    filename = f"{agent.memory.current_business_key}-pl-{today}.pdf"
    return StreamingResponse(
        iter([pdf_bytes]), media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/api/ledger")
def get_ledger(
    page: int = 1, page_size: int = 20, search: str = "",
    from_date: str = "", to_date: str = "",
    current_user: dict = Depends(require_owner_or_bookkeeper),
) -> dict:
    page_size = min(max(page_size, 1), 100)
    page = max(page, 1)
    with agent_lock:
        profile = agent.memory.get_current_business()
        if not profile.get("google_sheet_id"):
            return {"rows": [], "total_count": 0, "page": page, "page_size": page_size, "total_pages": 0}
        rows = agent.sheets.read_range(spreadsheet_id=profile["google_sheet_id"], range_name="Ledger!A1:G")
        data_rows = rows[1:] if rows and rows[0][:len(agent.LEDGER_HEADERS)] == agent.LEDGER_HEADERS else rows
        filtered = []
        for row in data_rows:
            if len(row) < 2:
                continue
            date_str = str(row[0]).strip()
            if from_date and date_str < from_date:
                continue
            if to_date and date_str > to_date:
                continue
            if search:
                desc = str(row[1]).lower() if len(row) > 1 else ""
                cat = str(row[2]).lower() if len(row) > 2 else ""
                if search.lower() not in desc and search.lower() not in cat:
                    continue
            filtered.append(agent._normalize_row(row))
        total_count = len(filtered)
        total_pages = max(1, (total_count + page_size - 1) // page_size)
        start = (page - 1) * page_size
        return {
            "rows": filtered[start: start + page_size],
            "total_count": total_count, "page": page,
            "page_size": page_size, "total_pages": total_pages,
        }


@router.get("/api/balance-sheet")
def get_balance_sheet(
    from_date: Optional[str] = None, to_date: Optional[str] = None,
    current_user: dict = Depends(require_owner_or_bookkeeper),
) -> dict:
    with agent_lock:
        profile = agent.memory.get_current_business()
        if not profile.get("google_sheet_id"):
            raise HTTPException(status_code=400, detail="No Google Sheet configured")
        rows = agent.sheets.read_range(
            spreadsheet_id=profile["google_sheet_id"], range_name="Ledger!A2:G1000",
        )
        if from_date or to_date:
            filtered = [
                row for row in rows[1:] if len(row) >= 1
                and (not from_date or str(row[0]) >= from_date)
                and (not to_date or str(row[0]) <= to_date)
            ]
            rows = [rows[0]] + filtered
        ar_ap_data = None
        try:
            ar_ap_data = agent.memory.load_ar_ap()
        except Exception:  # noqa: BLE001
            pass
        return agent.financial_statements.compute_balance_sheet(rows[1:], ar_ap_data)


@router.get("/api/cash-flow")
def get_cash_flow(
    from_date: Optional[str] = None, to_date: Optional[str] = None,
    current_user: dict = Depends(require_owner_or_bookkeeper),
) -> dict:
    with agent_lock:
        profile = agent.memory.get_current_business()
        if not profile.get("google_sheet_id"):
            raise HTTPException(status_code=400, detail="No Google Sheet configured")
        rows = agent.sheets.read_range(
            spreadsheet_id=profile["google_sheet_id"], range_name="Ledger!A2:G1000",
        )
        if from_date or to_date:
            filtered = [
                row for row in rows[1:] if len(row) >= 1
                and (not from_date or str(row[0]) >= from_date)
                and (not to_date or str(row[0]) <= to_date)
            ]
            rows = [rows[0]] + filtered
        period_start = from_date or "2026-01-01"
        period_end = to_date or datetime.now().strftime("%Y-%m-%d")
        return agent.financial_statements.compute_cash_flow(rows[1:], period_start, period_end)
