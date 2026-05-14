"""Creates and ensures Google Workspace assets (Sheet + Doc) for a business."""
from __future__ import annotations

from typing import Any


def ensure_business_workspace_assets(
    memory: Any,
    sheets: Any,
    docs: Any,
    workbook_ready: set,
) -> dict[str, Any]:
    profile = memory.get_current_business()
    updates: dict[str, str] = {}
    business_name = profile["business_name"]
    if not profile.get("google_sheet_id") or profile["google_sheet_id"].startswith("replace-with-"):
        spreadsheet = sheets.create_spreadsheet(
            title=f"{business_name} CPA Ledger",
            worksheet_name="Ledger",
            header_row=["Date", "Description", "Category", "Amount", "Type", "Reference", "Notes"],
        )
        updates["google_sheet_id"] = spreadsheet["spreadsheetId"]
    target_sheet_id = updates.get("google_sheet_id", profile.get("google_sheet_id", ""))
    if target_sheet_id and target_sheet_id not in workbook_ready:
        sheets.ensure_financial_workbook(
            spreadsheet_id=target_sheet_id,
            business_name=business_name,
        )
        workbook_ready.add(target_sheet_id)
    if not profile.get("google_doc_id") or str(profile["google_doc_id"]).startswith("replace-with-"):
        document = docs.create_document(
            title=f"{business_name} CPA Notes",
            initial_text=(
                f"{business_name} working paper\n"
                "This document is managed by CPA-Agent.\n"
            ),
        )
        updates["google_doc_id"] = document["documentId"]
    if updates:
        profile = memory.update_business_profile(memory.current_business_key, updates)
    return profile
