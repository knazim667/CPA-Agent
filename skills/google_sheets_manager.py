from __future__ import annotations

import os
from typing import Any

from core.google_auth import GoogleWorkspaceAuth


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

    def create_spreadsheet(
        self,
        title: str,
        worksheet_name: str = "Ledger",
        header_row: list[str] | None = None,
    ) -> dict[str, Any]:
        spreadsheet = (
            self._get_service()
            .spreadsheets()
            .create(
                body={
                    "properties": {"title": title},
                    "sheets": [{"properties": {"title": worksheet_name}}],
                }
            )
            .execute()
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
            self._get_service()
            .spreadsheets()
            .batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"requests": [{"updateSpreadsheetProperties": {"properties": {"title": title}, "fields": "title"}}]},
            )
            .execute()
        )

    def ensure_ledger_sheet(
        self,
        spreadsheet_id: str,
        worksheet_name: str = "Ledger",
        header_row: list[str] | None = None,
    ) -> dict[str, Any]:
        spreadsheet = self._get_service().spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        sheet_names = {sheet["properties"]["title"] for sheet in spreadsheet.get("sheets", [])}
        if worksheet_name not in sheet_names:
            self._get_service().spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"requests": [{"addSheet": {"properties": {"title": worksheet_name}}}]},
            ).execute()
        if header_row:
            self.update_range(
                spreadsheet_id=spreadsheet_id,
                range_name=f"{worksheet_name}!A1:{self._column_letter(len(header_row))}1",
                values=[header_row],
            )
        return self._get_service().spreadsheets().get(spreadsheetId=spreadsheet_id).execute()

    def ensure_financial_workbook(self, spreadsheet_id: str, business_name: str) -> dict[str, Any]:
        spreadsheet = self._get_service().spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        sheets = spreadsheet.get("sheets", [])
        by_name = {sheet["properties"]["title"]: sheet["properties"]["sheetId"] for sheet in sheets}
        requests_body = {"requests": []}

        for title in ("Ledger", "P&L Summary", "Dashboard"):
            if title not in by_name:
                requests_body["requests"].append({"addSheet": {"properties": {"title": title}}})

        if requests_body["requests"]:
            self._get_service().spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body=requests_body,
            ).execute()
            spreadsheet = self._get_service().spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
            sheets = spreadsheet.get("sheets", [])
            by_name = {sheet["properties"]["title"]: sheet["properties"]["sheetId"] for sheet in sheets}

        self.update_range(
            spreadsheet_id=spreadsheet_id,
            range_name="Ledger!A1:G1",
            values=[["Date", "Description", "Category", "Amount", "Type", "Reference", "Notes"]],
        )
        self.update_range(
            spreadsheet_id=spreadsheet_id,
            range_name="P&L Summary!A1:B5",
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
            range_name="Dashboard!A1:B6",
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
        return self._get_service().spreadsheets().get(spreadsheetId=spreadsheet_id).execute()

    def read_range(self, spreadsheet_id: str, range_name: str) -> list[list[str]]:
        response = (
            self._get_service()
            .spreadsheets()
            .values()
            .get(spreadsheetId=spreadsheet_id, range=range_name)
            .execute()
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
            self._get_service()
            .spreadsheets()
            .values()
            .append(
                spreadsheetId=spreadsheet_id,
                range=f"{worksheet_name}!A:Z",
                valueInputOption="USER_ENTERED",
                insertDataOption="INSERT_ROWS",
                body=body,
            )
            .execute()
        )

    def update_range(
        self,
        spreadsheet_id: str,
        range_name: str,
        values: list[list[Any]],
    ) -> dict[str, Any]:
        return (
            self._get_service()
            .spreadsheets()
            .values()
            .update(
                spreadsheetId=spreadsheet_id,
                range=range_name,
                valueInputOption="USER_ENTERED",
                body={"values": values},
            )
            .execute()
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
            self._get_service()
            .spreadsheets()
            .batchUpdate(spreadsheetId=spreadsheet_id, body=requests_body)
            .execute()
        )

    def apply_accounting_layout(self, spreadsheet_id: str, sheet_map: dict[str, int]) -> dict[str, Any]:
        requests_body = {
            "requests": [
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_map["Ledger"],
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
                        "properties": {"sheetId": sheet_map["Ledger"], "gridProperties": {"frozenRowCount": 1}},
                        "fields": "gridProperties.frozenRowCount",
                    }
                },
                {
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": sheet_map["Ledger"],
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
                            "sheetId": sheet_map["Ledger"],
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
                            "sheetId": sheet_map["P&L Summary"],
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
                            "sheetId": sheet_map["Dashboard"],
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
                            "sheetId": sheet_map["Dashboard"],
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
                            "sheetId": sheet_map["Dashboard"],
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
                            "sheetId": sheet_map["Dashboard"],
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
        self.format_currency_column(spreadsheet_id, sheet_map["Ledger"], 3, 4)
        self.format_currency_column(spreadsheet_id, sheet_map["P&L Summary"], 1, 2)
        return {"ok": True}

    @staticmethod
    def _column_letter(column_number: int) -> str:
        result = []
        while column_number > 0:
            column_number, remainder = divmod(column_number - 1, 26)
            result.append(chr(65 + remainder))
        return "".join(reversed(result))
