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

    @staticmethod
    def _column_letter(column_number: int) -> str:
        result = []
        while column_number > 0:
            column_number, remainder = divmod(column_number - 1, 26)
            result.append(chr(65 + remainder))
        return "".join(reversed(result))
