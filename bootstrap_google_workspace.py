from __future__ import annotations

from pathlib import Path

from memory_manager import MemoryManager
from skills import GoogleDocsManager, GoogleSheetsManager


ROOT_DIR = Path(__file__).resolve().parent


def ensure_assets_for_business(memory: MemoryManager, business_key: str) -> dict:
    memory.switch_business(business_key)
    profile = memory.get_current_business()
    sheets = GoogleSheetsManager()
    docs = GoogleDocsManager()
    updates = {}

    if not profile.get("google_sheet_id") or str(profile["google_sheet_id"]).startswith("replace-with-"):
        spreadsheet = sheets.create_spreadsheet(
            title=f"{profile['business_name']} CPA Ledger",
            worksheet_name="Ledger",
            header_row=["Date", "Description", "Category", "Amount", "Type", "Reference", "Notes"],
        )
        updates["google_sheet_id"] = spreadsheet["spreadsheetId"]

    sheet_id = updates.get("google_sheet_id", profile.get("google_sheet_id"))
    if sheet_id:
        sheets.ensure_ledger_sheet(
            spreadsheet_id=sheet_id,
            worksheet_name="Ledger",
            header_row=["Date", "Description", "Category", "Amount", "Type", "Reference", "Notes"],
        )

    if not profile.get("google_doc_id") or str(profile["google_doc_id"]).startswith("replace-with-"):
        document = docs.create_document(
            title=f"{profile['business_name']} CPA Notes",
            initial_text=f"{profile['business_name']} working paper\nThis document is managed by CPA-Agent.\n",
        )
        updates["google_doc_id"] = document["documentId"]

    if updates:
        profile = memory.update_business_profile(business_key, updates)
    return profile


def main() -> int:
    memory = MemoryManager(ROOT_DIR / "memory")
    for business_key in sorted(path.name for path in (ROOT_DIR / "memory" / "long_term").iterdir() if path.is_dir()):
        profile = ensure_assets_for_business(memory, business_key)
        print(
            f"{profile['business_name']}: "
            f"sheet={profile.get('google_sheet_id')} "
            f"doc={profile.get('google_doc_id')}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
