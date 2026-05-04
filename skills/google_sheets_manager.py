from __future__ import annotations

import os
from typing import Any

from core.google_auth import GoogleWorkspaceAuth


SHEET_LEDGER = "Ledger"
SHEET_PNL = "P&L Summary"
SHEET_DASHBOARD = "Dashboard"


class GoogleSheetsManager:
    """Thin Google Sheets wrapper for business-specific ledger access."""

    def __init__(self, credentials_path: str | None = None) -> None:
        self.credentials_path = credentials_path or os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
        self.auth = GoogleWorkspaceAuth(self.credentials_path)
        self._service = None

    def _get_service(self):
        if self._service is None:
            self._service = self.auth.build_service("sheets", "v4")
        return self._service

    def _reset_service(self) -> None:
        self._service = None
        self.auth._services.pop("sheets:v4", None)

    @staticmethod
    def _is_broken_pipe_error(exc: Exception) -> bool:
        if isinstance(exc, BrokenPipeError):
            return True
        return isinstance(exc, OSError) and getattr(exc, "errno", None) == 32

    def _execute(self, request_factory):
        try:
            return request_factory(self._get_service()).execute()
        except Exception as exc:  # noqa: BLE001
            if not self._is_broken_pipe_error(exc):
                raise
            self._reset_service()
            return request_factory(self._get_service()).execute()

    def create_spreadsheet(
        self,
        title: str,
        worksheet_name: str = "Ledger",
        header_row: list[str] | None = None,
    ) -> dict[str, Any]:
        spreadsheet = (
            self._execute(
                lambda service: service.spreadsheets().create(
                    body={
                        "properties": {"title": title},
                        "sheets": [{"properties": {"title": worksheet_name}}],
                    }
                )
            )
        )
        spreadsheet_id = spreadsheet["spreadsheetId"]
        if header_row:
            self.update_range(
                spreadsheet_id=spreadsheet_id,
                range_name=f"{worksheet_name}!A1:{self._column_letter(len(header_row))}1",
                values=[header_row],
            )
        return spreadsheet

    def rename_spreadsheet(self, spreadsheet_id: str, title: str) -> dict[str, Any]:
        return (
            self._execute(
                lambda service: service.spreadsheets().batchUpdate(
                    spreadsheetId=spreadsheet_id,
                    body={"requests": [{"updateSpreadsheetProperties": {"properties": {"title": title}, "fields": "title"}}]},
                )
            )
        )

    def ensure_ledger_sheet(
        self,
        spreadsheet_id: str,
        worksheet_name: str = "Ledger",
        header_row: list[str] | None = None,
    ) -> dict[str, Any]:
        spreadsheet = self._execute(lambda service: service.spreadsheets().get(spreadsheetId=spreadsheet_id))
        sheet_names = {sheet["properties"]["title"] for sheet in spreadsheet.get("sheets", [])}
        if worksheet_name not in sheet_names:
            self._execute(
                lambda service: service.spreadsheets().batchUpdate(
                    spreadsheetId=spreadsheet_id,
                    body={"requests": [{"addSheet": {"properties": {"title": worksheet_name}}}]},
                )
            )
        if header_row:
            self.update_range(
                spreadsheet_id=spreadsheet_id,
                range_name=f"{worksheet_name}!A1:{self._column_letter(len(header_row))}1",
                values=[header_row],
            )
        return self._execute(lambda service: service.spreadsheets().get(spreadsheetId=spreadsheet_id))

    def ensure_financial_workbook(self, spreadsheet_id: str, business_name: str) -> dict[str, Any]:
        spreadsheet = self._execute(lambda service: service.spreadsheets().get(spreadsheetId=spreadsheet_id))
        sheets = spreadsheet.get("sheets", [])
        by_name = {sheet["properties"]["title"]: sheet["properties"]["sheetId"] for sheet in sheets}
        requests_body = {"requests": []}

        for title in (SHEET_LEDGER, SHEET_PNL, SHEET_DASHBOARD):
            if title not in by_name:
                requests_body["requests"].append({"addSheet": {"properties": {"title": title}}})

        if requests_body["requests"]:
            self._execute(
                lambda service: service.spreadsheets().batchUpdate(
                    spreadsheetId=spreadsheet_id,
                    body=requests_body,
                )
            )
            spreadsheet = self._execute(lambda service: service.spreadsheets().get(spreadsheetId=spreadsheet_id))
            sheets = spreadsheet.get("sheets", [])
            by_name = {sheet["properties"]["title"]: sheet["properties"]["sheetId"] for sheet in sheets}

        self.update_range(
            spreadsheet_id=spreadsheet_id,
            range_name=f"{SHEET_LEDGER}!A1:G1",
            values=[["Date", "Description", "Category", "Amount", "Type", "Reference", "Notes"]],
        )
        self.update_range(
            spreadsheet_id=spreadsheet_id,
            range_name=f"{SHEET_PNL}!A1:B5",
            values=[
                [f"{business_name} Profit & Loss", ""],
                ["Metric", "Value"],
                ["Total Income", '=SUMIF(Ledger!E:E,"Income",Ledger!D:D)'],
                ["Total Expenses", '=SUMIF(Ledger!E:E,"Expense",Ledger!D:D)'],
                ["Net Profit", "=B3-B4"],
            ],
        )
        self.update_range(
            spreadsheet_id=spreadsheet_id,
            range_name=f"{SHEET_DASHBOARD}!A1:B6",
            values=[
                [f"{business_name} Dashboard", ""],
                ["Latest Update", '=IF(COUNTA(Ledger!A:A)>1,MAX(Ledger!A2:A),"")'],
                ["Transactions", '=MAX(COUNTA(Ledger!A:A)-1,0)'],
                ["Income", '=SUMIF(Ledger!E:E,"Income",Ledger!D:D)'],
                ["Expenses", '=SUMIF(Ledger!E:E,"Expense",Ledger!D:D)'],
                ["Net", "=B4-B5"],
            ],
        )
        self.apply_accounting_layout(spreadsheet_id, by_name)
        return self._execute(lambda service: service.spreadsheets().get(spreadsheetId=spreadsheet_id))

    def read_range(self, spreadsheet_id: str, range_name: str) -> list[list[str]]:
        response = (
            self._execute(
                lambda service: service.spreadsheets().values().get(
                    spreadsheetId=spreadsheet_id,
                    range=range_name,
                )
            )
        )
        return response.get("values", [])

    def append_ledger_row(
        self,
        spreadsheet_id: str,
        worksheet_name: str,
        row_values: list[Any],
    ) -> dict[str, Any]:
        body = {"values": [row_values]}
        return (
            self._execute(
                lambda service: service.spreadsheets().values().append(
                    spreadsheetId=spreadsheet_id,
                    range=f"{worksheet_name}!A:Z",
                    valueInputOption="USER_ENTERED",
                    insertDataOption="INSERT_ROWS",
                    body=body,
                )
            )
        )

    def find_duplicate_row(
        self,
        spreadsheet_id: str,
        date: str,
        amount: str | float,
        entry_type: str,
        lookback_rows: int = 100,
    ) -> dict[str, Any] | None:
        """Return the first row matching date+amount+type within the last lookback_rows, or None."""
        rows = self.read_range(spreadsheet_id, f"Ledger!A2:G{1 + lookback_rows}")
        target_date = str(date).strip()
        target_amount = str(amount).strip()
        target_type = str(entry_type).strip().lower()
        for row in rows:
            if len(row) < 5:
                continue
            if (
                str(row[0]).strip() == target_date
                and str(row[3]).strip() == target_amount
                and str(row[4]).strip().lower() == target_type
            ):
                return {
                    "date": row[0],
                    "description": row[1] if len(row) > 1 else "",
                    "amount": row[3],
                    "type": row[4],
                }
        return None

    def get_sheet_id(self, spreadsheet_id: str, sheet_name: str = "Ledger") -> int:
        """Return the numeric sheetId for the named worksheet."""
        spreadsheet = self._execute(lambda service: service.spreadsheets().get(spreadsheetId=spreadsheet_id))
        for sheet in spreadsheet.get("sheets", []):
            if sheet["properties"]["title"] == sheet_name:
                return sheet["properties"]["sheetId"]
        raise ValueError(f"Sheet '{sheet_name}' not found in spreadsheet {spreadsheet_id}")

    def delete_rows(self, spreadsheet_id: str, sheet_id: int, row_indices: list[int]) -> dict[str, Any]:
        """Delete rows by their 0-based sheet indices. Deletes bottom-to-top to avoid index drift."""
        requests = [
            {
                "deleteDimension": {
                    "range": {
                        "sheetId": sheet_id,
                        "dimension": "ROWS",
                        "startIndex": idx,
                        "endIndex": idx + 1,
                    }
                }
            }
            for idx in sorted(row_indices, reverse=True)
        ]
        return self._execute(
            lambda service: service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"requests": requests},
            )
        )

    def find_duplicate_ledger_rows(self, spreadsheet_id: str) -> list[dict]:
        """Return duplicate ledger rows (all but the first occurrence of each date+amount+type group)."""
        rows = self.read_range(spreadsheet_id, "Ledger!A2:G1000")
        seen: dict[tuple, int] = {}
        duplicates = []
        for i, row in enumerate(rows):
            if len(row) < 5:
                continue
            key = (str(row[0]).strip(), str(row[3]).strip(), str(row[4]).strip().lower())
            if key in seen:
                # 0-based sheet index: header is index 0, data row i is index i+1
                duplicates.append({
                    "sheet_row_index": i + 1,
                    "date": row[0],
                    "description": row[1] if len(row) > 1 else "",
                    "amount": row[3],
                    "type": row[4],
                })
            else:
                seen[key] = i
        return duplicates

    def update_range(
        self,
        spreadsheet_id: str,
        range_name: str,
        values: list[list[Any]],
    ) -> dict[str, Any]:
        return (
            self._execute(
                lambda service: service.spreadsheets().values().update(
                    spreadsheetId=spreadsheet_id,
                    range=range_name,
                    valueInputOption="USER_ENTERED",
                    body={"values": values},
                )
            )
        )

    def format_currency_column(
        self,
        spreadsheet_id: str,
        sheet_id: int,
        start_column_index: int,
        end_column_index: int,
    ) -> dict[str, Any]:
        requests_body = {
            "requests": [
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startColumnIndex": start_column_index,
                            "endColumnIndex": end_column_index,
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "numberFormat": {
                                    "type": "CURRENCY",
                                    "pattern": "$#,##0.00",
                                }
                            }
                        },
                        "fields": "userEnteredFormat.numberFormat",
                    }
                }
            ]
        }
        return (
            self._execute(
                lambda service: service.spreadsheets().batchUpdate(
                    spreadsheetId=spreadsheet_id,
                    body=requests_body,
                )
            )
        )

    def apply_accounting_layout(self, spreadsheet_id: str, sheet_map: dict[str, int]) -> dict[str, Any]:
        requests_body = {
            "requests": [
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_map[SHEET_LEDGER],
                            "startRowIndex": 0,
                            "endRowIndex": 1,
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "backgroundColor": {"red": 0.12, "green": 0.44, "blue": 0.37},
                                "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True},
                            }
                        },
                        "fields": "userEnteredFormat(backgroundColor,textFormat)",
                    }
                },
                {
                    "updateSheetProperties": {
                        "properties": {"sheetId": sheet_map[SHEET_LEDGER], "gridProperties": {"frozenRowCount": 1}},
                        "fields": "gridProperties.frozenRowCount",
                    }
                },
                {
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": sheet_map[SHEET_LEDGER],
                            "dimension": "COLUMNS",
                            "startIndex": 0,
                            "endIndex": 7,
                        },
                        "properties": {"pixelSize": 160},
                        "fields": "pixelSize",
                    }
                },
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_map[SHEET_LEDGER],
                            "startColumnIndex": 0,
                            "endColumnIndex": 1,
                            "startRowIndex": 1,
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "numberFormat": {
                                    "type": "DATE",
                                    "pattern": "mm/dd/yyyy",
                                }
                            }
                        },
                        "fields": "userEnteredFormat.numberFormat",
                    }
                },
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_map[SHEET_PNL],
                            "startRowIndex": 0,
                            "endRowIndex": 2,
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "textFormat": {"bold": True},
                                "backgroundColor": {"red": 0.96, "green": 0.95, "blue": 0.88},
                            }
                        },
                        "fields": "userEnteredFormat(textFormat,backgroundColor)",
                    }
                },
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_map[SHEET_DASHBOARD],
                            "startRowIndex": 0,
                            "endRowIndex": 1,
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "textFormat": {"bold": True},
                                "backgroundColor": {"red": 0.9, "green": 0.94, "blue": 0.93},
                            }
                        },
                        "fields": "userEnteredFormat(textFormat,backgroundColor)",
                    }
                },
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_map[SHEET_DASHBOARD],
                            "startColumnIndex": 1,
                            "endColumnIndex": 2,
                            "startRowIndex": 1,
                            "endRowIndex": 2,
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "numberFormat": {
                                    "type": "DATE",
                                    "pattern": "mm/dd/yyyy",
                                }
                            }
                        },
                        "fields": "userEnteredFormat.numberFormat",
                    }
                },
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_map[SHEET_DASHBOARD],
                            "startColumnIndex": 1,
                            "endColumnIndex": 2,
                            "startRowIndex": 2,
                            "endRowIndex": 3,
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "numberFormat": {
                                    "type": "NUMBER",
                                    "pattern": "0",
                                }
                            }
                        },
                        "fields": "userEnteredFormat.numberFormat",
                    }
                },
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_map[SHEET_DASHBOARD],
                            "startColumnIndex": 1,
                            "endColumnIndex": 2,
                            "startRowIndex": 3,
                            "endRowIndex": 6,
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "numberFormat": {
                                    "type": "CURRENCY",
                                    "pattern": "$#,##0.00",
                                }
                            }
                        },
                        "fields": "userEnteredFormat.numberFormat",
                    }
                },
            ]
        }
        self._get_service().spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body=requests_body,
        ).execute()
        self.format_currency_column(spreadsheet_id, sheet_map[SHEET_LEDGER], 3, 4)
        self.format_currency_column(spreadsheet_id, sheet_map[SHEET_PNL], 1, 2)
        return {"ok": True}

    @staticmethod
    def _column_letter(column_number: int) -> str:
        result = []
        while column_number > 0:
            column_number, remainder = divmod(column_number - 1, 26)
            result.append(chr(65 + remainder))
        return "".join(reversed(result))
