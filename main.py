from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
import speech_recognition as sr

from core.ollama_client import OllamaClient
from memory_manager import MemoryManager
from skills import GoogleDocsManager, GoogleSheetsManager, KnowledgeManager


ROOT_DIR = Path(__file__).resolve().parent
PERSONA_DIR = ROOT_DIR / "persona"
SYSTEM_PROMPT_PATH = PERSONA_DIR / "system_prompt.md"
CUSTOM_RULES_PATH = PERSONA_DIR / "custom_rules.json"


class CPAAgent:
    LEDGER_HEADERS = [
        "Date",
        "Description",
        "Category",
        "Amount",
        "Type",
        "Reference",
        "Notes",
    ]

    def __init__(self) -> None:
        self.memory = MemoryManager(ROOT_DIR / "memory")
        self.ollama = OllamaClient()
        self.sheets = GoogleSheetsManager()
        self.docs = GoogleDocsManager()
        self.knowledge = KnowledgeManager()
        self.recognizer = sr.Recognizer()
        self.recognizer.pause_threshold = 0.8
        self.wake_words = ("hey cpa-agent", "hey cpa agent", "cpa-agent", "cpa agent")
        self.input_mode = self._determine_input_mode()
        self.workspace_boot_error: str | None = None
        self._load_persona_assets()
        try:
            self.ensure_business_workspace_assets()
        except Exception as exc:  # noqa: BLE001
            self.workspace_boot_error = str(exc)

    def _determine_input_mode(self) -> str:
        forced_mode = os.getenv("CPA_AGENT_INPUT_MODE", "").strip().lower()
        if forced_mode in {"text", "voice"}:
            return forced_mode

        try:
            with sr.Microphone():
                return "voice"
        except OSError:
            return "text"

    def _load_persona_assets(self) -> None:
        self.system_prompt = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
        with CUSTOM_RULES_PATH.open("r", encoding="utf-8") as handle:
            self.custom_rules = json.load(handle)

    def refresh_rules(self) -> None:
        with CUSTOM_RULES_PATH.open("r", encoding="utf-8") as handle:
            self.custom_rules = json.load(handle)

    def speak(self, message: str) -> None:
        safe_message = shlex.quote(message)
        subprocess.run(f"say {safe_message}", shell=True, check=False)

    def listen_for_command(self) -> str | None:
        if self.input_mode == "text":
            try:
                typed = input("CPA-Agent command> ").strip()
            except EOFError:
                return "exit"
            return typed or None

        with sr.Microphone() as source:
            print("Listening for wake word...")
            self.recognizer.adjust_for_ambient_noise(source, duration=1)
            audio = self.recognizer.listen(source)

        try:
            transcript = self.recognizer.recognize_google(audio).lower().strip()
        except (sr.UnknownValueError, sr.RequestError):
            return None

        if any(wake_word in transcript for wake_word in self.wake_words):
            cleaned = transcript
            for wake_word in self.wake_words:
                cleaned = cleaned.replace(wake_word, "")
            return cleaned.strip(" ,.")
        return None

    def build_messages(self, user_input: str) -> list[dict[str, str]]:
        self.refresh_rules()
        business = self.memory.get_current_business()
        short_term = self.memory.load_short_term_context()
        learned_context = self._build_learned_context()
        custom_rules = json.dumps(self.custom_rules, indent=2)
        business_context = json.dumps(business, indent=2)
        short_term_context = json.dumps(short_term, indent=2)

        system_content = (
            f"{self.system_prompt}\n\n"
            "Custom correction rules that must be applied before every action:\n"
            f"{custom_rules}\n\n"
            "Current active business silo:\n"
            f"{business_context}\n\n"
            "Current short-term context:\n"
            f"{short_term_context}\n\n"
            "Learned operating knowledge:\n"
            f"{learned_context}"
        )

        return [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_input},
        ]

    def run_reasoning(self, user_input: str) -> dict[str, Any]:
        response_text = self.ollama.chat(self.build_messages(user_input))
        return self.extract_action_plan(response_text)

    def extract_action_plan(self, response_text: str) -> dict[str, Any]:
        try:
            start = response_text.index("{")
            end = response_text.rindex("}") + 1
            return json.loads(response_text[start:end])
        except (ValueError, json.JSONDecodeError):
            return {
                "thought": "Model returned plain text; no tool action extracted.",
                "action": "respond",
                "parameters": {},
                "response": response_text.strip(),
            }

    def execute_action(self, plan: dict[str, Any], user_input: str) -> dict[str, Any]:
        action = plan.get("action", "respond")
        parameters = plan.get("parameters", {})

        if action == "switch_business":
            business_name = parameters.get("business_name") or self.detect_business_switch(user_input)
            if not business_name:
                raise ValueError("Business switch requested without a business name.")
            new_profile = self.memory.switch_business(business_name)
            return {
                "status": "success",
                "message": f"Switched to {new_profile['business_name']}.",
                "details": new_profile,
            }

        if action == "record_transaction":
            profile = self.ensure_business_workspace_assets()
            values = self._normalize_bulk_values(parameters.get("values"))
            if not values:
                inferred_values = self._infer_bulk_values_from_user_input(user_input, parameters)
                if inferred_values:
                    values = inferred_values
            row_values = self._build_row_values_from_plan(parameters)
            worksheet_name = parameters.get("worksheet_name", "Ledger")
            sheet_url = self._sheet_url(profile["google_sheet_id"])

            if values:
                start_row = self._next_ledger_row_number(profile["google_sheet_id"], worksheet_name)
                end_row = start_row + len(values) - 1
                range_name = parameters.get("range") or f"{worksheet_name}!A{start_row}:G{end_row}"
                result = self.sheets.update_range(
                    spreadsheet_id=profile["google_sheet_id"],
                    range_name=range_name,
                    values=values,
                )
                verification = self._verify_sheet_write(
                    spreadsheet_id=profile["google_sheet_id"],
                    range_name=range_name,
                )
                self._record_transaction_audit(
                    mode="bulk_update",
                    requested_payload=values,
                    result=result,
                    verification=verification,
                )
                if not verification["verified"]:
                    return {
                        "status": "needs_review",
                        "message": "I could not verify that the transaction rows were written to the sheet.",
                        "details": {
                            "result": result,
                            "verification": verification,
                            "sheet_url": sheet_url,
                        },
                    }
                return {
                    "status": "success",
                    "message": f"Transactions recorded. Sheet: {sheet_url}",
                    "details": {
                        "result": result,
                        "verification": verification,
                        "sheet_url": sheet_url,
                    },
                }

            if not row_values:
                return {
                    "status": "needs_review",
                    "message": "I could not record that transaction because the ledger row was incomplete.",
                    "details": {
                        "plan_parameters": parameters,
                        "sheet_url": sheet_url,
                    },
                }

            result = self.sheets.append_ledger_row(
                spreadsheet_id=profile["google_sheet_id"],
                worksheet_name=worksheet_name,
                row_values=row_values,
            )
            updated_range = result.get("updates", {}).get("updatedRange")
            verification = self._verify_sheet_write(
                spreadsheet_id=profile["google_sheet_id"],
                range_name=updated_range or f"{worksheet_name}!A:Z",
            )
            self._record_transaction_audit(
                mode="append",
                requested_payload=row_values,
                result=result,
                verification=verification,
            )
            if not verification["verified"]:
                return {
                    "status": "needs_review",
                    "message": "I could not verify that the transaction was written to the sheet.",
                    "details": {
                        "result": result,
                        "verification": verification,
                        "sheet_url": sheet_url,
                    },
                }
            return {
                "status": "success",
                "message": f"Transaction recorded. Sheet: {sheet_url}",
                "details": {
                    "result": result,
                    "verification": verification,
                    "sheet_url": sheet_url,
                },
            }

        if action == "read_sheet":
            profile = self.ensure_business_workspace_assets()
            values = self.sheets.read_range(
                spreadsheet_id=profile["google_sheet_id"],
                range_name=parameters.get("range_name", "Ledger!A1:Z20"),
            )
            return {"status": "success", "message": "Sheet data retrieved.", "details": values}

        if action == "create_business_doc":
            profile = self.ensure_business_workspace_assets()
            return {
                "status": "success",
                "message": "Business document is ready.",
                "details": {"document_id": profile["google_doc_id"]},
            }

        if action == "append_doc_note":
            profile = self.ensure_business_workspace_assets()
            result = self.docs.append_text(
                document_id=profile["google_doc_id"],
                text=parameters.get("text", ""),
            )
            return {"status": "success", "message": "Document note saved.", "details": result}

        return {
            "status": "success",
            "message": plan.get("response", "No tool call was needed."),
            "details": {"action": action, "parameters": parameters},
        }

    def record_structured_transaction(
        self,
        *,
        date: str,
        description: str,
        category: str,
        amount: float,
        entry_type: str,
        reference: str = "",
        notes: str = "",
    ) -> dict[str, Any]:
        profile = self.ensure_business_workspace_assets()
        sheet_url = self._sheet_url(profile["google_sheet_id"])
        normalized_type = entry_type.strip().title()
        amount_value = round(float(amount), 2)
        row_values = [
            date.strip(),
            description.strip(),
            category.strip(),
            amount_value,
            normalized_type,
            reference.strip(),
            notes.strip(),
        ]
        draft_result = {
            "status": "success",
            "message": (
                f"Prepared a {normalized_type.lower()} transaction for {description.strip()} "
                f"for ${amount_value:.2f}."
            ),
            "details": {
                "business": profile["business_name"],
                "row_values": row_values,
            },
        }
        reflection = self.self_reflect(
            user_input=(
                f"Record {normalized_type.lower()} transaction: {description.strip()} "
                f"({category.strip()}) for ${amount_value:.2f} on {date.strip()}."
            ),
            draft_result=draft_result,
        )
        if not reflection.get("approved"):
            return {
                "ok": False,
                "message": reflection.get(
                    "corrected_message",
                    "I found a possible issue during verification and paused the transaction.",
                ),
                "reflection": reflection,
            }

        result = self.sheets.append_ledger_row(
            spreadsheet_id=profile["google_sheet_id"],
            worksheet_name="Ledger",
            row_values=row_values,
        )
        updated_range = result.get("updates", {}).get("updatedRange")
        verification = self._verify_sheet_write(
            spreadsheet_id=profile["google_sheet_id"],
            range_name=updated_range or "Ledger!A:Z",
        )
        self._record_transaction_audit(
            mode="structured_append",
            requested_payload=row_values,
            result=result,
            verification=verification,
        )
        if not verification["verified"]:
            return {
                "ok": False,
                "message": "I could not verify that the structured transaction was written to the sheet.",
                "details": {
                    "result": result,
                    "verification": verification,
                    "sheet_url": sheet_url,
                },
            }
        outcome = {
            "status": "success",
            "message": (
                reflection.get("corrected_message")
                or f"Recorded {normalized_type.lower()} transaction for {description.strip()}."
            )
            + f" Sheet: {sheet_url}",
            "details": {
                "result": result,
                "verification": verification,
                "sheet_url": sheet_url,
            },
        }
        user_input = (
            f"Structured transaction: {normalized_type.lower()} {description.strip()} "
            f"for ${amount_value:.2f} in {category.strip()}."
        )
        self.memory.record_skill_outcome(
            action_name="record_transaction",
            success=True,
            details={
                "user_input": user_input,
                "draft_result": draft_result,
                "reflection": reflection,
                "row_values": row_values,
            },
        )
        self.update_short_term_memory(user_input, outcome)
        return {
            "ok": True,
            "message": outcome["message"],
            "details": {
                "append_result": result,
                "verification": verification,
                "row_values": row_values,
                "sheet_url": sheet_url,
            },
        }

    def list_businesses(self) -> list[dict[str, str]]:
        businesses = []
        for key in self.memory.list_business_keys():
            profile = self.memory.load_business_profile(key)
            businesses.append(
                {
                    "key": key,
                    "business_name": profile["business_name"],
                }
            )
        return businesses

    def get_dashboard_snapshot(self) -> dict[str, Any]:
        current = self.memory.get_current_business()
        skill_memory = self.memory.load_skill_memory()
        transaction_audit = self.memory.load_transaction_audit().get("entries", [])
        conversation = self.memory.load_short_term_context().get("conversation", [])

        totals = {
            "income_total": 0.0,
            "expense_total": 0.0,
            "transaction_count": 0,
            "recent_transactions": [],
        }
        if current.get("google_sheet_id"):
            try:
                rows = self.sheets.read_range(
                    spreadsheet_id=current["google_sheet_id"],
                    range_name="Ledger!A1:G50",
                )
                totals = self._summarize_ledger_rows(rows)
            except Exception as exc:  # noqa: BLE001
                totals["ledger_error"] = str(exc)

        success_history = [item for item in skill_memory.get("history", []) if item.get("success")]
        failure_history = [item for item in skill_memory.get("history", []) if not item.get("success")]
        recent_audits = [entry for entry in transaction_audit if entry.get("business") == self.memory.current_business_key][-5:]
        return {
            "active_business_name": current["business_name"],
            "transaction_count": totals["transaction_count"],
            "income_total": round(totals["income_total"], 2),
            "expense_total": round(totals["expense_total"], 2),
            "recent_transactions": totals["recent_transactions"],
            "recent_audits": recent_audits,
            "conversation_count": len(conversation),
            "successful_actions": len(success_history),
            "flagged_actions": len(failure_history),
            "ledger_error": totals.get("ledger_error"),
        }

    def get_status(self) -> dict[str, Any]:
        short_term = self.memory.load_short_term_context()
        current = self.memory.get_current_business()
        return {
            "active_business_key": self.memory.current_business_key,
            "active_business": current,
            "businesses": self.list_businesses(),
            "conversation": short_term.get("conversation", []),
            "workspace_boot_error": self.workspace_boot_error,
            "input_mode": self.input_mode,
            "dashboard": self.get_dashboard_snapshot(),
            "learned_source_count": len(self.memory.load_learned_sources().get("entries", [])),
        }

    def _summarize_ledger_rows(self, rows: list[list[Any]]) -> dict[str, Any]:
        if not rows:
            return {
                "income_total": 0.0,
                "expense_total": 0.0,
                "transaction_count": 0,
                "recent_transactions": [],
            }

        data_rows = rows[1:] if rows[0][: len(self.LEDGER_HEADERS)] == self.LEDGER_HEADERS else rows
        income_total = 0.0
        expense_total = 0.0
        parsed_rows: list[dict[str, Any]] = []

        for row in data_rows:
            if len(row) < 5:
                continue
            amount = self._safe_float(row[3] if len(row) > 3 else 0)
            entry_type = str(row[4]).strip().lower()
            record = {
                "date": str(row[0]) if len(row) > 0 else "",
                "description": str(row[1]) if len(row) > 1 else "",
                "category": str(row[2]) if len(row) > 2 else "",
                "amount": round(amount, 2),
                "type": str(row[4]) if len(row) > 4 else "",
                "reference": str(row[5]) if len(row) > 5 else "",
                "notes": str(row[6]) if len(row) > 6 else "",
            }
            parsed_rows.append(record)
            if entry_type == "income":
                income_total += amount
            else:
                expense_total += amount

        return {
            "income_total": income_total,
            "expense_total": expense_total,
            "transaction_count": len(parsed_rows),
            "recent_transactions": list(reversed(parsed_rows[-5:])),
        }

    def _build_row_values_from_plan(self, parameters: dict[str, Any]) -> list[Any]:
        row_values = parameters.get("row_values")
        if row_values:
            return self._normalize_row(row_values)
        if parameters.get("date") and parameters.get("description") and parameters.get("amount") is not None:
            category = parameters.get("category") or parameters.get("account") or "Uncategorized"
            transaction_type = parameters.get("type") or parameters.get("entry_type") or "Expense"
            return self._normalize_row([
                parameters.get("date", ""),
                parameters.get("description", ""),
                category,
                parameters.get("amount", ""),
                transaction_type,
                parameters.get("reference", ""),
                parameters.get("notes", ""),
            ])
        return []

    def _normalize_bulk_values(self, values: Any) -> list[list[Any]]:
        if not values or not isinstance(values, list):
            return []
        normalized = []
        for row in values:
            if isinstance(row, list):
                normalized_row = self._normalize_row(row)
                if normalized_row:
                    normalized.append(normalized_row)
        return normalized

    def _normalize_row(self, row: list[Any]) -> list[Any]:
        normalized = list(row[:7])
        while len(normalized) < 7:
            normalized.append("")
        if len(normalized) >= 5 and not normalized[4]:
            normalized[4] = "Expense"
        if len(normalized) >= 3 and not normalized[2]:
            normalized[2] = "Uncategorized"
        return normalized

    def _infer_bulk_values_from_user_input(self, user_input: str, parameters: dict[str, Any]) -> list[list[Any]]:
        lines = [line.strip(" -\t") for line in user_input.splitlines() if line.strip()]
        extracted_items: list[tuple[str, float]] = []
        for line in lines:
            match = re.match(r"(.+?)\s*[:\-]\s*\$?([0-9]+(?:\.[0-9]{1,2})?)$", line)
            if match:
                extracted_items.append((match.group(1).strip(), float(match.group(2))))
        if not extracted_items:
            return []

        default_category = parameters.get("category") or parameters.get("account") or "Start-up Costs"
        entry_type = parameters.get("type") or parameters.get("entry_type") or "Expense"
        date_map = self._infer_dates_from_text(user_input)
        fallback_date = parameters.get("date") or date_map.get("default") or ""
        rows = []
        for description, amount in extracted_items:
            description_key = description.lower()
            matched_date = fallback_date
            preferred_keywords = ("nozzle", "filament", "sample", "caliper", "glue", "printing", "table", "cable")
            for keyword in preferred_keywords:
                if keyword in description_key and keyword in date_map:
                    matched_date = date_map[keyword]
                    break
            else:
                prioritized_keywords = sorted(
                    ((keyword, mapped_date) for keyword, mapped_date in date_map.items() if keyword != "default"),
                    key=lambda item: len(item[0]),
                    reverse=True,
                )
                for keyword, mapped_date in prioritized_keywords:
                    if keyword in description_key:
                        matched_date = mapped_date
                        break
            rows.append(
                self._normalize_row(
                    [
                        matched_date,
                        description,
                        default_category,
                        amount,
                        entry_type,
                        "",
                        parameters.get("notes", ""),
                    ]
                )
            )
        return rows

    def _infer_dates_from_text(self, text: str) -> dict[str, str]:
        mappings: dict[str, str] = {}
        for match in re.finditer(
            r"(?P<label>[A-Za-z0-9 /]+?)\s+(?:is on|on|dated)\s+(?P<date>\d{1,2}/\d{1,2}/\d{4})",
            text,
            re.IGNORECASE,
        ):
            label = match.group("label").strip().lower()
            mappings[label] = match.group("date")
            if "printer" in label:
                mappings["printer"] = match.group("date")
        generic_dates = re.findall(r"\b\d{1,2}/\d{1,2}/\d{4}\b", text)
        if generic_dates and "default" not in mappings:
            mappings["default"] = generic_dates[-1]
        if "others things i bought" in text.lower() and len(generic_dates) >= 2:
            mappings["cable"] = generic_dates[-1]
            mappings["table"] = generic_dates[-1]
            mappings["printing"] = generic_dates[-1]
            mappings["caliper"] = generic_dates[-1]
            mappings["glue"] = generic_dates[-1]
            mappings["nozzle"] = generic_dates[-1]
            mappings["sample"] = generic_dates[-1]
            mappings["filament"] = generic_dates[-1]
        return mappings

    def _next_ledger_row_number(self, spreadsheet_id: str, worksheet_name: str) -> int:
        rows = self.sheets.read_range(spreadsheet_id=spreadsheet_id, range_name=f"{worksheet_name}!A:A")
        return max(2, len(rows) + 1)

    @staticmethod
    def _sheet_url(spreadsheet_id: str) -> str:
        return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"

    def _verify_sheet_write(self, spreadsheet_id: str, range_name: str) -> dict[str, Any]:
        try:
            values = self.sheets.read_range(spreadsheet_id=spreadsheet_id, range_name=range_name)
            verified = any(any(str(cell).strip() for cell in row) for row in values)
            return {
                "verified": verified,
                "range_name": range_name,
                "values": values,
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "verified": False,
                "range_name": range_name,
                "error": str(exc),
            }

    def _record_transaction_audit(
        self,
        *,
        mode: str,
        requested_payload: Any,
        result: dict[str, Any],
        verification: dict[str, Any],
    ) -> None:
        self.memory.record_transaction_audit(
            {
                "timestamp": time.time(),
                "business": self.memory.current_business_key,
                "mode": mode,
                "requested_payload": requested_payload,
                "result": result,
                "verification": verification,
            }
        )

    def _build_learned_context(self) -> str:
        entries = self.memory.load_learned_sources().get("entries", [])
        if not entries:
            return "No learned sources stored yet."
        lines = []
        for entry in entries[-6:]:
            domain = urlparse(entry.get("url", "")).netloc or "source"
            lines.append(
                f"- {entry.get('title', 'Untitled')} ({domain}): {entry.get('summary', '')[:280]}"
            )
        return "\n".join(lines)

    @staticmethod
    def _safe_float(value: Any) -> float:
        if isinstance(value, (int, float)):
            return float(value)
        cleaned = str(value).replace("$", "").replace(",", "").strip()
        try:
            return float(cleaned)
        except ValueError:
            return 0.0

    def ensure_business_workspace_assets(self) -> dict[str, Any]:
        profile = self.memory.get_current_business()
        updates: dict[str, str] = {}
        business_name = profile["business_name"]

        if not profile.get("google_sheet_id") or profile["google_sheet_id"].startswith("replace-with-"):
            spreadsheet = self.sheets.create_spreadsheet(
                title=f"{business_name} CPA Ledger",
                worksheet_name="Ledger",
                header_row=[
                    "Date",
                    "Description",
                    "Category",
                    "Amount",
                    "Type",
                    "Reference",
                    "Notes",
                ],
            )
            updates["google_sheet_id"] = spreadsheet["spreadsheetId"]

        target_sheet_id = updates.get("google_sheet_id", profile.get("google_sheet_id", ""))
        if target_sheet_id:
            self.sheets.ensure_financial_workbook(
                spreadsheet_id=target_sheet_id,
                business_name=business_name,
            )

        if not profile.get("google_doc_id") or str(profile["google_doc_id"]).startswith("replace-with-"):
            document = self.docs.create_document(
                title=f"{business_name} CPA Notes",
                initial_text=(
                    f"{business_name} working paper\n"
                    "This document is managed by CPA-Agent.\n"
                ),
            )
            updates["google_doc_id"] = document["documentId"]

        if updates:
            profile = self.memory.update_business_profile(self.memory.current_business_key, updates)
        elif target_sheet_id:
            self.sheets.ensure_financial_workbook(
                spreadsheet_id=target_sheet_id,
                business_name=business_name,
            )
        return profile

    def self_reflect(self, user_input: str, draft_result: dict[str, Any]) -> dict[str, Any]:
        reflection_prompt = [
            {
                "role": "system",
                "content": (
                    "You are the CPA-Agent safety verifier. Review the proposed result for math mistakes, "
                    "business silo leakage, unsupported tax claims, and risky accounting categorization. "
                    "Respond only in JSON with keys approved, concerns, corrected_message."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "user_input": user_input,
                        "active_business": self.memory.get_current_business(),
                        "draft_result": draft_result,
                        "custom_rules": self.custom_rules,
                    },
                    indent=2,
                ),
            },
        ]
        reflection_text = self.ollama.chat(reflection_prompt)
        try:
            start = reflection_text.index("{")
            end = reflection_text.rindex("}") + 1
            return json.loads(reflection_text[start:end])
        except (ValueError, json.JSONDecodeError):
            return {
                "approved": False,
                "concerns": ["Reflection step returned malformed output."],
                "corrected_message": "I need a manual review before I confirm that action.",
            }

    def update_short_term_memory(self, user_input: str, outcome: dict[str, Any]) -> None:
        self.memory.append_conversation_entry(
            {
                "timestamp": time.time(),
                "business": self.memory.current_business_key,
                "user_input": user_input,
                "outcome": outcome,
            }
        )

    def detect_business_switch(self, user_input: str) -> str | None:
        match = re.search(r"switch to ([a-zA-Z0-9_ -]+)", user_input, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return None

    def detect_business_rename(self, user_input: str) -> str | None:
        patterns = (
            r"(?:rename|change)\s+(?:the\s+)?(?:current\s+)?business(?:\s+\w+)?\s+to\s+([A-Za-z0-9 _-]+)",
            r"update\s+(?:the\s+)?business\s+name\s+to\s+([A-Za-z0-9 _-]+)",
        )
        for pattern in patterns:
            match = re.search(pattern, user_input, re.IGNORECASE)
            if match:
                return match.group(1).strip(" .")
        return None

    @staticmethod
    def extract_learning_urls(user_input: str) -> list[str]:
        return re.findall(r"https?://[^\s)]+", user_input)

    @staticmethod
    def is_learning_request(user_input: str) -> bool:
        lowered = user_input.lower()
        markers = ("learn", "study", "read this", "use this doc", "research this", "for the agent")
        return any(marker in lowered for marker in markers)

    @staticmethod
    def is_recalculation_request(user_input: str) -> bool:
        lowered = user_input.lower()
        markers = ("re-check", "recheck", "recalculate", "fix the accounts", "check for errors", "fix if there is error")
        return any(marker in lowered for marker in markers)

    def maybe_store_correction_rule(self, user_input: str) -> None:
        lowered = user_input.lower()
        correction_markers = (
            "no, that's",
            "no that is",
            "actually,",
            "correction:",
            "you should classify",
            "it should be",
        )
        if not any(marker in lowered for marker in correction_markers):
            return

        self.memory.record_custom_rule(
            user_input=user_input,
            destination_path=CUSTOM_RULES_PATH,
        )
        self.refresh_rules()

    def handle_command(self, user_input: str) -> str:
        if not user_input:
            return "I heard the wake word, but not the request."

        self.maybe_store_correction_rule(user_input)

        if self.is_recalculation_request(user_input):
            result = self.recalculate_accounts()
            message = self._clean_response_text(result["message"])
            self.update_short_term_memory(user_input, {"message": message, "details": result})
            return message

        rename_target = self.detect_business_rename(user_input)
        if rename_target:
            profile = self.rename_current_business(rename_target)
            message = f"Renamed the active business to {profile['business_name']}."
            self.update_short_term_memory(user_input, {"message": message})
            return message

        learn_urls = self.extract_learning_urls(user_input)
        if learn_urls and self.is_learning_request(user_input):
            result = self.learn_from_urls(learn_urls, topic="google_workspace")
            message = (
                f"Learned from {result['count']} source(s). "
                "I'll use this knowledge for future Google Sheets and Docs work."
            )
            self.update_short_term_memory(user_input, {"message": message, "details": result})
            return message

        switch_target = self.detect_business_switch(user_input)
        if switch_target:
            profile = self.memory.switch_business(switch_target)
            profile = self.ensure_business_workspace_assets()
            message = f"Switched to {profile['business_name']}."
            self.update_short_term_memory(user_input, {"message": message})
            return message

        plan = self.run_reasoning(user_input)
        draft_result = self.execute_action(plan, user_input)
        reflection = self.self_reflect(user_input, draft_result)

        if reflection.get("approved"):
            final_message = reflection.get("corrected_message") or draft_result["message"]
        else:
            final_message = reflection.get(
                "corrected_message",
                "I found a possible issue during verification and paused the action.",
            )
            draft_result["status"] = "needs_review"
            draft_result["reflection_concerns"] = reflection.get("concerns", [])

        self.memory.record_skill_outcome(
            action_name=plan.get("action", "respond"),
            success=bool(reflection.get("approved")),
            details={
                "user_input": user_input,
                "plan": plan,
                "draft_result": draft_result,
                "reflection": reflection,
            },
        )
        self.update_short_term_memory(user_input, draft_result)
        return self._clean_response_text(final_message)

    def handle_command_with_metadata(self, user_input: str) -> dict[str, Any]:
        message = self.handle_command(user_input)
        status = self.get_status()
        conversation = status.get("conversation", [])
        latest_outcome = conversation[-1].get("outcome", {}) if conversation else {}
        presentation = self._build_presentation(latest_outcome, status, message)
        return {
            "message": message,
            "status": status,
            "presentation": presentation,
        }

    def recalculate_accounts(self) -> dict[str, Any]:
        profile = self.ensure_business_workspace_assets()
        workbook = self.sheets.ensure_financial_workbook(
            spreadsheet_id=profile["google_sheet_id"],
            business_name=profile["business_name"],
        )
        dashboard = self.get_dashboard_snapshot()
        return {
            "message": (
                f"I rechecked the workbook for {profile['business_name']}. "
                f"Transactions: {dashboard['transaction_count']}. "
                f"Income: ${dashboard['income_total']:.2f}. "
                f"Expenses: ${dashboard['expense_total']:.2f}. "
                f"Sheet: {self._sheet_url(profile['google_sheet_id'])}"
            ),
            "dashboard": dashboard,
            "workbook": workbook,
        }

    @staticmethod
    def _clean_response_text(text: str) -> str:
        cleaned = text.replace("**", "").replace("###", "").replace("---", "\n")
        cleaned = cleaned.replace("•", "-")
        if cleaned.count("|") > 6:
            cleaned = re.sub(r"\|\s*[-:]+\s*", "|", cleaned)
            cleaned = cleaned.replace("|", "\n")
        cleaned = re.sub(r"\s{2,}", " ", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        cleaned = re.sub(r" +\n", "\n", cleaned)
        cleaned = re.sub(r"\n +", "\n", cleaned)
        return cleaned.strip()

    def _build_presentation(self, outcome: dict[str, Any], status: dict[str, Any], message: str) -> dict[str, Any] | None:
        details = outcome.get("details", {}) if isinstance(outcome, dict) else {}
        dashboard = status.get("dashboard", {})
        active_business = status.get("active_business", {})

        if isinstance(details, dict) and "sheet_url" in details:
            verification = details.get("verification", {})
            rows = verification.get("values", []) if isinstance(verification, dict) else []
            normalized_rows = [self._normalize_row(row) for row in rows if isinstance(row, list)]
            total = 0.0
            for row in normalized_rows:
                total += self._safe_float(row[3])
            return {
                "kind": "transaction_result",
                "title": f"{active_business.get('business_name', 'Business')} Ledger Update",
                "sheet_url": details.get("sheet_url"),
                "summary_items": [
                    {"label": "Rows Written", "value": str(len(normalized_rows))},
                    {"label": "Verified", "value": "Yes" if verification.get("verified") else "No"},
                    {"label": "Total Amount", "value": f"${total:.2f}"},
                ],
                "table": {
                    "columns": self.LEDGER_HEADERS,
                    "rows": normalized_rows,
                },
            }

        if isinstance(details, dict) and "dashboard" in details:
            dashboard_payload = details["dashboard"]
            return {
                "kind": "account_review",
                "title": f"{active_business.get('business_name', 'Business')} Account Review",
                "summary_items": [
                    {"label": "Transactions", "value": str(dashboard_payload.get("transaction_count", 0))},
                    {"label": "Income", "value": f"${dashboard_payload.get('income_total', 0):.2f}"},
                    {"label": "Expenses", "value": f"${dashboard_payload.get('expense_total', 0):.2f}"},
                    {"label": "Flagged", "value": str(dashboard_payload.get("flagged_actions", 0))},
                ],
            }

        if isinstance(details, dict) and details.get("count"):
            entries = details.get("entries", [])
            return {
                "kind": "learning_result",
                "title": "Knowledge Updated",
                "summary_items": [
                    {"label": "Sources Learned", "value": str(details.get("count", 0))},
                    {"label": "Stored Sources", "value": str(status.get("learned_source_count", 0))},
                ],
                "sources": [
                    {"title": entry.get("title", "Untitled"), "url": entry.get("url", "")}
                    for entry in entries
                ],
            }

        if dashboard and ("sheet:" in message.lower() or "rechecked the workbook" in message.lower()):
            return {
                "kind": "account_review",
                "title": f"{active_business.get('business_name', 'Business')} Account Review",
                "summary_items": [
                    {"label": "Transactions", "value": str(dashboard.get("transaction_count", 0))},
                    {"label": "Income", "value": f"${dashboard.get('income_total', 0):.2f}"},
                    {"label": "Expenses", "value": f"${dashboard.get('expense_total', 0):.2f}"},
                    {"label": "Flagged", "value": str(dashboard.get("flagged_actions", 0))},
                ],
            }

        return None

    def rename_current_business(self, new_name: str) -> dict[str, Any]:
        profile = self.memory.update_business_profile(
            self.memory.current_business_key,
            {"business_name": new_name.strip()},
        )
        if profile.get("google_sheet_id"):
            try:
                self.sheets.rename_spreadsheet(
                    spreadsheet_id=profile["google_sheet_id"],
                    title=f"{profile['business_name']} CPA Ledger",
                )
            except Exception as exc:  # noqa: BLE001
                self.workspace_boot_error = str(exc)
        if profile.get("google_doc_id"):
            try:
                self.docs.rename_document(
                    document_id=profile["google_doc_id"],
                    title=f"{profile['business_name']} CPA Notes",
                )
            except Exception as exc:  # noqa: BLE001
                self.workspace_boot_error = str(exc)
        return profile

    def learn_from_urls(self, urls: list[str], topic: str = "") -> dict[str, Any]:
        entries = []
        for url in urls:
            page = self.knowledge.learn_from_url(url)
            entry = self.knowledge.make_memory_entry(page, topic=topic)
            self.memory.record_learned_source(entry)
            entries.append(entry)
        return {"count": len(entries), "entries": entries}

    def run(self) -> None:
        current = self.memory.get_current_business()
        print(f"CPA-Agent ready. Active business: {current['business_name']}")
        print(f"Input mode: {self.input_mode}")
        self.speak(f"CPA-Agent is ready for {current['business_name']}.")

        while True:
            try:
                command = self.listen_for_command()
            except OSError:
                self.input_mode = "text"
                print("No microphone detected. Switched to text input mode.")
                continue
            if command is None:
                continue
            if command.lower() in {"quit", "exit", "stop listening"}:
                self.speak("CPA-Agent signing off.")
                break

            try:
                response = self.handle_command(command)
            except requests.RequestException as exc:
                response = f"I hit a network issue: {exc}"
            except Exception as exc:  # noqa: BLE001
                response = f"I could not complete that safely: {exc}"

            print(f"User: {command}")
            print(f"CPA-Agent: {response}")
            self.speak(response)


def main() -> int:
    agent = CPAAgent()
    agent.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
