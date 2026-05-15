"""Google Sheets formatting helpers — column letters, currency, accounting layout."""
from __future__ import annotations

from typing import Any, Callable

SHEET_LEDGER = "Ledger"
SHEET_PNL = "P&L Summary"
SHEET_DASHBOARD = "Dashboard"


def column_letter(column_number: int) -> str:
    result = []
    while column_number > 0:
        column_number, remainder = divmod(column_number - 1, 26)
        result.append(chr(65 + remainder))
    return "".join(reversed(result))


def format_currency_column(
    execute_fn: Callable,
    spreadsheet_id: str,
    sheet_id: int,
    start_column_index: int,
    end_column_index: int,
) -> dict[str, Any]:
    return execute_fn(
        lambda service: service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
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
                                    "numberFormat": {"type": "CURRENCY", "pattern": "$#,##0.00"}
                                }
                            },
                            "fields": "userEnteredFormat.numberFormat",
                        }
                    }
                ]
            },
        )
    )


def apply_accounting_layout(
    execute_fn: Callable,
    format_fn: Callable,
    spreadsheet_id: str,
    sheet_map: dict[str, int],
) -> dict[str, Any]:
    requests_body = {
        "requests": [
            {
                "repeatCell": {
                    "range": {"sheetId": sheet_map[SHEET_LEDGER], "startRowIndex": 0, "endRowIndex": 1},
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
                        "sheetId": sheet_map[SHEET_LEDGER], "dimension": "COLUMNS",
                        "startIndex": 0, "endIndex": 7,
                    },
                    "properties": {"pixelSize": 160},
                    "fields": "pixelSize",
                }
            },
            {
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_map[SHEET_LEDGER],
                        "startColumnIndex": 0, "endColumnIndex": 1, "startRowIndex": 1,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "numberFormat": {"type": "DATE", "pattern": "mm/dd/yyyy"}
                        }
                    },
                    "fields": "userEnteredFormat.numberFormat",
                }
            },
            {
                "repeatCell": {
                    "range": {"sheetId": sheet_map[SHEET_PNL], "startRowIndex": 0, "endRowIndex": 2},
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
                    "range": {"sheetId": sheet_map[SHEET_DASHBOARD], "startRowIndex": 0, "endRowIndex": 1},
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
                        "startColumnIndex": 1, "endColumnIndex": 2, "startRowIndex": 1, "endRowIndex": 2,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "numberFormat": {"type": "DATE", "pattern": "mm/dd/yyyy"}
                        }
                    },
                    "fields": "userEnteredFormat.numberFormat",
                }
            },
            {
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_map[SHEET_DASHBOARD],
                        "startColumnIndex": 1, "endColumnIndex": 2, "startRowIndex": 2, "endRowIndex": 3,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "numberFormat": {"type": "NUMBER", "pattern": "0"}
                        }
                    },
                    "fields": "userEnteredFormat.numberFormat",
                }
            },
            {
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_map[SHEET_DASHBOARD],
                        "startColumnIndex": 1, "endColumnIndex": 2, "startRowIndex": 3, "endRowIndex": 6,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "numberFormat": {"type": "CURRENCY", "pattern": "$#,##0.00"}
                        }
                    },
                    "fields": "userEnteredFormat.numberFormat",
                }
            },
        ]
    }
    execute_fn(
        lambda service: service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id, body=requests_body,
        )
    )
    format_fn(spreadsheet_id, sheet_map[SHEET_LEDGER], 3, 4)
    format_fn(spreadsheet_id, sheet_map[SHEET_PNL], 1, 2)
    return {"ok": True}
