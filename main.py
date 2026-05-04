from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
import speech_recognition as sr
from dotenv import load_dotenv

load_dotenv()

from core.model_client import get_model_client
from memory_manager import MemoryManager
from skills import GoogleDocsManager, GoogleSheetsManager, KnowledgeManager
from skills.categorization_engine import CategorizationEngine
from skills.recurring_engine import RecurringEngine
from skills.financial_statements import FinancialStatements
from skills.budget_engine import BudgetEngine
from skills.reconciliation_engine import ReconciliationEngine
from skills.ar_ap_engine import ARAPEngine
from skills.tax_engine import TaxEngine


ROOT_DIR = Path(__file__).resolve().parent
PERSONA_DIR = ROOT_DIR / "persona"
SYSTEM_PROMPT_PATH = PERSONA_DIR / "system_prompt.md"
CUSTOM_RULES_PATH = PERSONA_DIR / "custom_rules.json"

ACTION_SWITCH_BUSINESS = "switch_business"
ACTION_CREATE_BUSINESS = "create_business"
ACTION_RECORD_TRANSACTION = "record_transaction"
ACTION_READ_SHEET = "read_sheet"
ACTION_CREATE_BUSINESS_DOC = "create_business_doc"
ACTION_APPEND_DOC_NOTE = "append_doc_note"
ACTION_CALCULATE_PAYROLL = "calculate_payroll"
ACTION_RESEARCH_TAX = "research_tax"
ACTION_RESPOND = "respond"


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
        self.reasoning_mode = self._normalize_reasoning_mode(
            os.getenv("CPA_AGENT_REASONING_MODE", "fast")
        )
        self._refresh_model_clients()
        self.sheets = GoogleSheetsManager()
        self.docs = GoogleDocsManager()
        self.knowledge = KnowledgeManager()
        self.categorization = CategorizationEngine(
            rules_data=self.memory.load_category_rules()
        )
        self.recurring = RecurringEngine(
            recurring_data=self.memory.load_recurring()
        )
        self.financial_statements = FinancialStatements()
        self.budget_engine = BudgetEngine()
        self.reconciliation_engine = ReconciliationEngine()
        self.ar_ap_engine = ARAPEngine(self.memory)
        self.tax_engine = TaxEngine(self.memory)
        if not self.categorization._rules:
            try:
                profile = self.memory.get_current_business()
                if profile.get("google_sheet_id"):
                    rows = self.sheets.read_range(
                        spreadsheet_id=profile["google_sheet_id"],
                        range_name="Ledger!A2:G200",
                    )
                    count = self.categorization.backfill_rules_from_ledger(rows)
                    if count:
                        self._save_category_rules()
            except Exception:  # noqa: BLE001
                pass  # backfill is best-effort; don't block startup
        self.recognizer = sr.Recognizer()
        self.recognizer.pause_threshold = 0.8
        self.wake_words = ("hey cpa-agent", "hey cpa agent", "cpa-agent", "cpa agent")
        self.input_mode = self._determine_input_mode()
        self.workspace_boot_error: str | None = None
        self._workbook_ready: set[str] = set()
        self._load_persona_assets()
        try:
            self.ensure_business_workspace_assets()
        except Exception as exc:  # noqa: BLE001
            self.workspace_boot_error = str(exc)

    @staticmethod
    def _normalize_reasoning_mode(value: str) -> str:
        normalized = (value or "fast").strip().lower()
        return normalized if normalized in {"fast", "quality"} else "fast"

    def _refresh_model_clients(self) -> None:
        self.model_client = get_model_client(purpose="reasoning", reasoning_mode=self.reasoning_mode)
        self.reflection_client = get_model_client(purpose="reflection", reasoning_mode=self.reasoning_mode)

    def set_reasoning_mode(self, mode: str) -> dict[str, str]:
        self.reasoning_mode = self._normalize_reasoning_mode(mode)
        os.environ["CPA_AGENT_REASONING_MODE"] = self.reasoning_mode
        self._refresh_model_clients()
        return self.get_model_status()

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

    def _save_category_rules(self) -> None:
        self.memory.save_category_rules(self.categorization.get_rules_data())

    def _save_recurring(self) -> None:
        self.memory.save_recurring(self.recurring.get_recurring_data())

    def refresh_rules(self) -> None:
        mtime = CUSTOM_RULES_PATH.stat().st_mtime
        if mtime == getattr(self, "_rules_mtime", None):
            return
        with CUSTOM_RULES_PATH.open("r", encoding="utf-8") as handle:
            self.custom_rules = json.load(handle)
        self._rules_mtime = mtime

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

    def _build_financial_context(self) -> str:
        """Build a compact summary of AR/AP and budget state for the LLM prompt."""
        parts = []
        try:
            overdue = self.ar_ap_engine.get_overdue_items()
            upcoming = self.ar_ap_engine.get_upcoming_due(days_ahead=7)
            overdue_r = len(overdue.get("receivables", []))
            overdue_p = len(overdue.get("payables", []))
            upcoming_p = len(upcoming.get("payables", []))
            if overdue_r or overdue_p or upcoming_p:
                parts.append(
                    f"AR/AP snapshot: {overdue_r} overdue receivable(s), "
                    f"{overdue_p} overdue payable(s), {upcoming_p} payable(s) due within 7 days."
                )
        except Exception:  # noqa: BLE001
            pass
        try:
            budget_data = self.memory.load_budgets()
            budgets = budget_data.get("budgets", [])
            if budgets:
                parts.append(f"Active budgets: {len(budgets)} monthly budget(s) set.")
        except Exception:  # noqa: BLE001
            pass
        return "\n".join(parts)

    def _enrich_with_category(self, user_input: str) -> str:
        """Prepend a suggested category hint to transaction-like inputs so the LLM doesn't guess blind."""
        lower = user_input.lower()
        is_transaction_intent = any(
            kw in lower for kw in ("record", "add", "log", "post", "expense", "income", "spent", "received", "paid")
        )
        if not is_transaction_intent:
            return user_input
        try:
            suggestion = self.categorization.suggest_category(user_input)
            if suggestion and suggestion.get("confidence", 0) >= 0.6:
                return (
                    f"[Suggested category from local rules: {suggestion['category']} "
                    f"(confidence {suggestion['confidence']:.0%})]\n{user_input}"
                )
        except Exception:  # noqa: BLE001
            pass
        return user_input

    def build_messages(self, user_input: str) -> list[dict[str, str]]:
        self.refresh_rules()
        business = self.memory.get_current_business()
        short_term = self.memory.load_short_term_context()
        learned_context = self._build_learned_context()
        financial_context = self._build_financial_context()
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
        )
        if financial_context:
            system_content += f"Current financial alerts:\n{financial_context}\n\n"
        system_content += f"Learned operating knowledge:\n{learned_context}"

        return [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_input},
        ]

    def run_reasoning(self, user_input: str) -> dict[str, Any]:
        response_text = self.model_client.chat(self.build_messages(user_input))
        return self.extract_action_plan(response_text)

    def extract_action_plan(self, response_text: str) -> dict[str, Any]:
        # Strip markdown code fences (e.g. ```json ... ```) before parsing
        text = re.sub(r"```(?:json)?\s*", "", response_text).strip().strip("`").strip()
        try:
            start = text.index("{")
            end = text.rindex("}") + 1
            return json.loads(text[start:end])
        except (ValueError, json.JSONDecodeError):
            return {
                "thought": "Model returned plain text; no tool action extracted.",
                "action": "respond",
                "parameters": {},
                "response": response_text.strip(),
            }

    def _parse_json_response(self, text: str) -> dict[str, Any] | None:
        try:
            start = text.index("{")
            end = text.rindex("}") + 1
            return json.loads(text[start:end])
        except (ValueError, json.JSONDecodeError):
            return None

    def execute_action(self, plan: dict[str, Any], user_input: str) -> dict[str, Any]:
        action = plan.get("action", ACTION_RESPOND)
        parameters = plan.get("parameters", {})

        if action == ACTION_SWITCH_BUSINESS:
            business_name = parameters.get("business_name") or self.detect_business_switch(user_input)
            if not business_name:
                raise ValueError("Business switch requested without a business name.")
            new_profile = self.memory.switch_business(business_name)
            return {
                "status": "success",
                "message": f"Switched to {new_profile['business_name']}.",
                "details": new_profile,
            }

        if action == ACTION_CREATE_BUSINESS:
            business_name = parameters.get("business_name") or self.detect_business_creation(user_input)
            if not business_name:
                raise ValueError("Business creation requested without a business name.")
            state = parameters.get("state", "")
            currency = parameters.get("default_books_currency", "USD")
            business_key, profile, created = self.memory.create_business(
                business_name,
                state=state,
                default_currency=currency,
            )
            sheet_url = None
            self.workspace_boot_error = None
            try:
                profile = self.ensure_business_workspace_assets()
                sheet_url = self._sheet_url(profile["google_sheet_id"])
            except Exception as exc:  # noqa: BLE001
                self.workspace_boot_error = str(exc)
            status = "success" if created else "noop"
            prefix = "Created" if created else "Switched to existing"
            message = f"{prefix} business {profile['business_name']}."
            if sheet_url:
                message = f"{message} Sheet: {sheet_url}"
            elif self.workspace_boot_error:
                message = f"{message} Local silo is ready, but Google workspace setup still needs attention."
            return {
                "status": status,
                "message": message,
                "details": {
                    "business_key": business_key,
                    "created": created,
                    "profile": profile,
                    "sheet_url": sheet_url,
                    "workspace_boot_error": self.workspace_boot_error,
                },
            }

        if action == ACTION_RECORD_TRANSACTION:
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

        if action == ACTION_READ_SHEET:
            profile = self.ensure_business_workspace_assets()
            values = self.sheets.read_range(
                spreadsheet_id=profile["google_sheet_id"],
                range_name=parameters.get("range_name", "Ledger!A1:Z20"),
            )
            return {"status": "success", "message": "Sheet data retrieved.", "details": values}

        if action == ACTION_CREATE_BUSINESS_DOC:
            profile = self.ensure_business_workspace_assets()
            return {
                "status": "success",
                "message": "Business document is ready.",
                "details": {"document_id": profile["google_doc_id"]},
            }

        if action == ACTION_APPEND_DOC_NOTE:
            profile = self.ensure_business_workspace_assets()
            result = self.docs.append_text(
                document_id=profile["google_doc_id"],
                text=parameters.get("text", ""),
            )
            return {"status": "success", "message": "Document note saved.", "details": result}

        if action == ACTION_CALCULATE_PAYROLL:
            from skills.payroll_engine import calculate_simple_payroll
            gross_pay = self._safe_float(parameters.get("gross_pay", 0))
            federal_rate = float(parameters.get("federal_rate", 0.12))
            if gross_pay <= 0:
                return {"status": "needs_review", "message": "Gross pay must be a positive number.", "details": {"parameters": parameters}}
            calc = calculate_simple_payroll(gross_pay=gross_pay, federal_rate=federal_rate)
            return {
                "status": "success",
                "message": f"Payroll: Gross ${calc.gross_pay:.2f} | Federal ${calc.federal_withholding:.2f} | SS ${calc.social_security:.2f} | Medicare ${calc.medicare:.2f} | Net ${calc.net_pay:.2f}.",
                "details": {"gross_pay": calc.gross_pay, "federal_withholding": calc.federal_withholding, "social_security": calc.social_security, "medicare": calc.medicare, "net_pay": calc.net_pay},
            }

        if action == ACTION_RESEARCH_TAX:
            from skills.tax_researcher import fetch_tax_update
            url = parameters.get("url", "").strip()
            if not url:
                return {"status": "needs_review", "message": "A URL is required for tax research.", "details": {}}
            result = fetch_tax_update(url)
            self.memory.record_learned_source({"url": result.url, "title": result.title, "summary": result.summary, "topic": "tax"})
            return {"status": "success", "message": f"Tax research complete. Stored: {result.title}", "details": {"url": result.url, "title": result.title, "summary": result.summary}}

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

        duplicate = self.sheets.find_duplicate_row(
            spreadsheet_id=profile["google_sheet_id"],
            date=date.strip(),
            amount=str(amount_value),
            entry_type=normalized_type,
        )
        if duplicate and "confirm duplicate" not in notes.lower():
            return {
                "ok": False,
                "message": (
                    f"Duplicate detected: a {duplicate['type']} of {duplicate['amount']} "
                    f"on {duplicate['date']} ({duplicate['description']}) already exists. "
                    "If this is intentional, add 'confirm duplicate' to the Notes field."
                ),
            }

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

    def record_bulk_transactions(
        self,
        rows: list[list[Any]],
        *,
        source_name: str = "",
        source_note: str = "",
    ) -> dict[str, Any]:
        profile = self.ensure_business_workspace_assets()
        sheet_url = self._sheet_url(profile["google_sheet_id"])
        normalized_rows = []
        for row in rows:
            normalized = self._normalize_row(row)
            if source_name and not normalized[5]:
                normalized[5] = source_name
            if source_note and not normalized[6]:
                normalized[6] = source_note
            normalized_rows.append(normalized)

        if not normalized_rows:
            return {
                "ok": False,
                "message": "There were no draft transactions to record.",
                "details": {"sheet_url": sheet_url},
            }

        draft_result = {
            "status": "success",
            "message": f"Prepared {len(normalized_rows)} transaction rows for approval.",
            "details": {
                "business": profile["business_name"],
                "rows": normalized_rows,
            },
        }
        reflection = self.self_reflect(
            user_input=f"Record {len(normalized_rows)} approved document-based transactions.",
            draft_result=draft_result,
        )
        if not reflection.get("approved"):
            return {
                "ok": False,
                "message": reflection.get(
                    "corrected_message",
                    "I found a possible issue during verification and paused these transactions.",
                ),
                "reflection": reflection,
            }

        start_row = self._next_ledger_row_number(profile["google_sheet_id"], "Ledger")
        end_row = start_row + len(normalized_rows) - 1
        range_name = f"Ledger!A{start_row}:G{end_row}"
        result = self.sheets.update_range(
            spreadsheet_id=profile["google_sheet_id"],
            range_name=range_name,
            values=normalized_rows,
        )
        verification = self._verify_sheet_write(
            spreadsheet_id=profile["google_sheet_id"],
            range_name=range_name,
        )
        self._record_transaction_audit(
            mode="approved_document_bulk_update",
            requested_payload=normalized_rows,
            result=result,
            verification=verification,
        )
        if not verification["verified"]:
            return {
                "ok": False,
                "message": "I could not verify that the approved document transactions were written to the sheet.",
                "details": {
                    "result": result,
                    "verification": verification,
                    "sheet_url": sheet_url,
                },
            }

        return {
            "ok": True,
            "message": f"Approved document transactions recorded. Sheet: {sheet_url}",
            "details": {
                "result": result,
                "verification": verification,
                "sheet_url": sheet_url,
                "rows": normalized_rows,
            },
        }

    def draft_document_transactions(
        self,
        *,
        file_name: str,
        document_text: str,
        instruction: str = "",
    ) -> dict[str, Any]:
        prompt = [
            {
                "role": "system",
                "content": (
                    "You are CPA-Agent drafting accounting entries from a source document. "
                    "Read the extracted document text and return only JSON with keys summary, rows, concerns. "
                    "Each row must contain date, description, category, amount, type, reference, notes. "
                    "Use multiple rows if the document has multiple purchases. "
                    "Be conservative and do not guess missing values."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "active_business": self.memory.get_current_business(),
                        "instruction": instruction,
                        "file_name": file_name,
                        "document_text": document_text[:12000],
                    },
                    indent=2,
                ),
            },
        ]
        response_text = self.model_client.chat(prompt)
        payload = self._parse_json_response(response_text)
        if payload is None:
            return {
                "ok": False,
                "message": "I could not convert that document into a clean draft table yet.",
                "details": {"raw_response": response_text},
            }

        raw_rows = payload.get("rows", [])
        rows = []
        for item in raw_rows:
            if not isinstance(item, dict):
                continue
            if item.get("amount") in (None, "") or not item.get("description"):
                continue
            rows.append(
                self._normalize_row(
                    [
                        item.get("date", ""),
                        item.get("description", ""),
                        item.get("category", "Uncategorized"),
                        item.get("amount", ""),
                        item.get("type", "Expense"),
                        item.get("reference", file_name),
                        item.get("notes", ""),
                    ]
                )
            )

        if not rows:
            return {
                "ok": False,
                "message": "I read the document, but I could not draft a reliable expense table from it.",
                "details": {
                    "summary": payload.get("summary", ""),
                    "concerns": payload.get("concerns", []),
                },
            }

        total_amount = sum(self._safe_float(row[3]) for row in rows)
        return {
            "ok": True,
            "message": (
                f"I prepared a draft with {len(rows)} row(s) totaling ${total_amount:.2f}. "
                "Review it and approve when you're ready."
            ),
            "details": {
                "summary": payload.get("summary", ""),
                "concerns": payload.get("concerns", []),
                "rows": rows,
                "total_amount": round(total_amount, 2),
                "file_name": file_name,
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
                    range_name="Ledger!A1:G2000",
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

    _STATUS_CACHE_TTL = 2.0  # seconds — deduplicates within-request calls

    def get_status(self) -> dict[str, Any]:
        now = time.monotonic()
        if hasattr(self, "_status_cache"):
            ts, cached = self._status_cache
            if now - ts < self._STATUS_CACHE_TTL:
                return cached
        result = self._build_status()
        self._status_cache = (now, result)
        return result

    def _build_status(self) -> dict[str, Any]:
        today_str = date.today().isoformat()
        due: list = []
        if today_str != getattr(self, "_last_schedule_check", None):
            due = self.recurring.run_due_schedules()
            self._last_schedule_check = today_str
        if due:
            self._save_recurring()
            for entry in due:
                try:
                    self.record_structured_transaction(
                        date=entry.get("last_posted_date", ""),
                        description=entry["description"],
                        category=entry["category"],
                        amount=entry["amount"],
                        entry_type=entry["entry_type"],
                        notes="Auto-posted by recurring schedule",
                    )
                except Exception as exc:  # noqa: BLE001
                    self.memory.record_skill_outcome(
                        action_name="recurring_auto_post",
                        success=False,
                        details={"error": str(exc), "entry": entry},
                    )

        short_term = self.memory.load_short_term_context()
        current = self.memory.get_current_business()
        raw_conv = short_term.get("conversation", [])
        conversation = []
        for entry in raw_conv:
            if entry.get("user_input"):
                conversation.append({"role": "user", "content": entry["user_input"]})
            if entry.get("outcome", {}).get("message"):
                conversation.append({"role": "agent", "content": entry["outcome"]["message"]})
        # Proactive AR/AP alerts — pure memory, no API cost
        overdue_ar_ap: dict = {"receivables": [], "payables": []}
        upcoming_ar_ap: dict = {"receivables": [], "payables": []}
        try:
            overdue_ar_ap = self.ar_ap_engine.get_overdue_items()
            upcoming_ar_ap = self.ar_ap_engine.get_upcoming_due(days_ahead=7)
        except Exception:  # noqa: BLE001
            pass

        return {
            "active_business_key": self.memory.current_business_key,
            "active_business": current,
            "businesses": self.list_businesses(),
            "conversation": conversation,
            "workspace_boot_error": self.workspace_boot_error,
            "input_mode": self.input_mode,
            "model_config": self.get_model_status(),
            "dashboard": self.get_dashboard_snapshot(),
            "learned_source_count": len(self.memory.load_learned_sources().get("entries", [])),
            "tax_alerts": self.tax_engine.get_upcoming_alerts(days_ahead=60),
            "overdue_ar_ap": overdue_ar_ap,
            "upcoming_ar_ap": upcoming_ar_ap,
        }

    def get_model_status(self) -> dict[str, str]:
        provider = os.getenv("MODEL_PROVIDER", "ollama").strip().lower() or "ollama"
        if provider == "ollama":
            reasoning_model = (
                os.getenv("OLLAMA_QUALITY_MODEL")
                if self.reasoning_mode == "quality" and os.getenv("OLLAMA_QUALITY_MODEL")
                else os.getenv("OLLAMA_MODEL", "gpt-oss:20b")
            )
            reflection_model = (
                os.getenv("OLLAMA_REFLECTION_MODEL")
                or os.getenv("OLLAMA_AUDIT_MODEL")
                or reasoning_model
            )
        elif provider == "openai":
            reasoning_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
            reflection_model = reasoning_model
        elif provider == "openrouter":
            reasoning_model = os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3-super-120b-a12b:free")
            reflection_model = reasoning_model
        else:
            reasoning_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
            reflection_model = reasoning_model
        return {
            "provider": provider,
            "reasoning_mode": self.reasoning_mode,
            "reasoning_model": reasoning_model,
            "reflection_model": reflection_model,
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
        text_lines = user_input.splitlines()
        rows = []
        for description, amount in extracted_items:
            matched_date = fallback_date
            desc_line_idx = next(
                (i for i, line in enumerate(text_lines) if description.lower() in line.lower()), -1
            )
            if desc_line_idx >= 0 and len(date_map) > 1:
                preceding = "\n".join(text_lines[: desc_line_idx + 1])
                preceding_dates = re.findall(r"\b\d{1,2}/\d{1,2}/\d{4}\b", preceding)
                if preceding_dates:
                    matched_date = preceding_dates[-1]
            for label, label_date in date_map.items():
                if label != "default" and label in description.lower():
                    matched_date = label_date
                    break
            rows.append(self._normalize_row([matched_date, description, default_category, amount, entry_type, "", parameters.get("notes", "")]))
        return rows

    def _infer_dates_from_text(self, text: str) -> dict[str, str]:
        mappings: dict[str, str] = {}
        all_dates = re.findall(r"\b\d{1,2}/\d{1,2}/\d{4}\b", text)
        if not all_dates:
            return mappings
        mappings["default"] = all_dates[-1]
        for match in re.finditer(
            r"(?P<label>[A-Za-z0-9 /]+?)\s+(?:is on|dated)\s+(?P<date>\d{1,2}/\d{1,2}/\d{4})",
            text,
            re.IGNORECASE,
        ):
            mappings[match.group("label").strip().lower()] = match.group("date")
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
        if target_sheet_id and target_sheet_id not in self._workbook_ready:
            self.sheets.ensure_financial_workbook(
                spreadsheet_id=target_sheet_id,
                business_name=business_name,
            )
            self._workbook_ready.add(target_sheet_id)

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
        reflection_text = self.reflection_client.chat(reflection_prompt)
        result = self._parse_json_response(reflection_text)
        if result is not None:
            return result
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

    def detect_business_creation(self, user_input: str) -> str | None:
        patterns = (
            r"(?:i\s+(?:started|launched|opened)|we\s+(?:started|launched|opened))\s+(?:a\s+)?(?:new\s+)?business(?:\s+called|\s+named)?\s+([A-Za-z0-9][A-Za-z0-9 &._-]*)",
            r"(?:create|add|set\s+up|setup)\s+(?:a\s+)?(?:new\s+)?business(?:\s+called|\s+named)?\s+([A-Za-z0-9][A-Za-z0-9 &._-]*)",
            r"(?:create|add)\s+business\s+([A-Za-z0-9][A-Za-z0-9 &._-]*)",
        )
        for pattern in patterns:
            match = re.search(pattern, user_input, re.IGNORECASE)
            if match:
                candidate = match.group(1).strip(" .")
                candidate = re.sub(r"\s+(please|for me|now)$", "", candidate, flags=re.IGNORECASE)
                if candidate:
                    return candidate
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

        create_target = self.detect_business_creation(user_input)
        if create_target:
            business_key, profile, created = self.memory.create_business(create_target)
            sheet_url = None
            self.workspace_boot_error = None
            try:
                profile = self.ensure_business_workspace_assets()
                sheet_url = self._sheet_url(profile["google_sheet_id"])
            except Exception as exc:  # noqa: BLE001
                self.workspace_boot_error = str(exc)
            if created:
                message = f"Created a new business silo for {profile['business_name']} and switched to it."
            else:
                message = f"{profile['business_name']} already existed, so I switched to it."
            if sheet_url:
                message = f"{message} Sheet: {sheet_url}"
            elif self.workspace_boot_error:
                message = f"{message} The local folder and config are ready, but Google workspace setup still needs attention."
            self.update_short_term_memory(
                user_input,
                {
                    "message": message,
                    "details": {
                        "business_key": business_key,
                        "created": created,
                        "profile": profile,
                        "sheet_url": sheet_url,
                        "workspace_boot_error": self.workspace_boot_error,
                    },
                },
            )
            return message

        switch_target = self.detect_business_switch(user_input)
        if switch_target:
            profile = self.memory.switch_business(switch_target)
            profile = self.ensure_business_workspace_assets()
            message = f"Switched to {profile['business_name']}."
            self.update_short_term_memory(user_input, {"message": message})
            return message

        plan = self.run_reasoning(self._enrich_with_category(user_input))
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
        self.update_short_term_memory(user_input, {**draft_result, "message": final_message})
        return self._clean_response_text(final_message)

    def detect_recurring_command(self, user_input: str) -> dict | None:
        lower = user_input.lower()
        m = re.search(
            r"schedule\s+(.+?)\s+\$?([\d,]+(?:\.\d{1,2})?)\s+(expense|income)\s+on\s+the\s+(\d+)(?:st|nd|rd|th)?\s+every\s+(\w+)",
            lower,
        )
        if m:
            return {
                "description": m.group(1).strip().title(),
                "amount": float(m.group(2).replace(",", "")),
                "entry_type": m.group(3).title(),
                "day_of_period": int(m.group(4)),
                "frequency": m.group(5).rstrip("s"),
            }
        if "cancel" in lower and "recurring" in lower:
            return {"cancel": True, "raw": user_input}
        if ("show" in lower or "list" in lower) and "recurring" in lower:
            return {"list": True}
        return None

    def detect_budget_command(self, user_input: str) -> dict | None:
        lower = user_input.lower()
        m = re.search(
            r"(?:set\s+)?(?P<cat>[a-z &]+?)\s+budget\s+\$?([\d,]+(?:\.\d{1,2})?)\s+(?:per\s+month|monthly|a\s+month)",
            lower,
        )
        if m:
            return {
                "category": m.group("cat").strip().title(),
                "amount": float(m.group(2).replace(",", "")),
            }
        if ("show" in lower or "list" in lower) and "budget" in lower:
            return {"list": True}
        return None

    def detect_reconcile_command(self, user_input: str) -> dict | None:
        lower = user_input.lower()
        # "reconcile bank statement" or "upload bank statement for reconciliation"
        if "reconcile" in lower and ("bank" in lower or "statement" in lower or "csv" in lower):
            return {"action": "reconcile"}
        return None

    def detect_ar_ap_command(self, user_input: str) -> dict | None:
        lower = user_input.lower()
        is_add = ("add" in lower or "create" in lower or "new" in lower)
        is_ar_keyword = ("receivable" in lower or "invoice" in lower or "owed" in lower)
        is_ap_keyword = ("bill" in lower or "payable" in lower)

        if is_add and (is_ar_keyword or is_ap_keyword):
            amount_match = re.search(r'\$?([\d,]+\.?\d*)', user_input)
            amount = float(amount_match.group(1).replace(',', '')) if amount_match else None
            cv_match = re.search(r'(?:from|for|to)\s+([A-Za-z0-9\s&]+?)(?:\s+\$|$)', lower)
            client_vendor = cv_match.group(1).strip().title() if cv_match else None
            action = "add_receivable" if is_ar_keyword else "add_payable"
            return {"action": action, "amount": amount, "client_vendor": client_vendor}

        if ("mark" in lower or "payment" in lower or "paid" in lower) and (is_ar_keyword or is_ap_keyword):
            entry_type = "receivable" if is_ar_keyword else "payable"
            return {"action": "mark_paid", "entry_type": entry_type}

        if ("show" in lower or "list" in lower or "get" in lower) and (is_ar_keyword or is_ap_keyword or "ar" in lower or "ap" in lower or "accounts" in lower):
            return {"action": "list_ar_ap"}

        if "overdue" in lower or "late" in lower:
            return {"action": "get_overdue"}

        return None

    def detect_tax_command(self, user_input: str) -> dict | None:
        lower = user_input.lower()
        # "tax estimate", "calculate tax", "what do i owe"
        if ("tax" in lower or "owe" in lower) and ("estimate" in lower or "calculate" in lower or "owe" in lower or "payment" in lower):
            return {"action": "get_tax_estimate"}

        # "tax deadline", "irs deadline", "when is tax due"
        if ("deadline" in lower or "due" in lower) and ("tax" in lower or "irs" in lower):
            return {"action": "get_tax_deadlines"}

        # "tax alert", "upcoming tax", "tax reminder"
        if ("alert" in lower or "reminder" in lower or "upcoming" in lower) and "tax" in lower:
            return {"action": "get_tax_alerts"}

        return None

    def detect_delete_command(self, user_input: str) -> dict | None:
        lower = user_input.lower()
        duplicate_words = ("duplicate", "duplicates", "dupes", "dupe")
        delete_words = ("delete", "remove", "clean", "clear", "deduplicate", "dedupe", "fix", "purge")
        if any(d in lower for d in duplicate_words) and any(w in lower for w in delete_words):
            return {"action": "delete_duplicates"}
        if "clean up" in lower and ("ledger" in lower or "transactions" in lower or "entries" in lower):
            return {"action": "delete_duplicates"}
        return None

    def delete_duplicate_ledger_rows(self) -> dict[str, Any]:
        profile = self.memory.get_current_business()
        spreadsheet_id = profile.get("google_sheet_id")
        if not spreadsheet_id:
            return {"ok": False, "message": "No Google Sheet configured for this business."}
        duplicates = self.sheets.find_duplicate_ledger_rows(spreadsheet_id)
        if not duplicates:
            return {"ok": True, "message": "No duplicate transactions found in the ledger. Everything looks clean."}
        sheet_id = self.sheets.get_sheet_id(spreadsheet_id, "Ledger")
        indices = [d["sheet_row_index"] for d in duplicates]
        self.sheets.delete_rows(spreadsheet_id, sheet_id, indices)
        lines = [f"  • {d['date']} | {d['description']} | {d['type']} ${d['amount']}" for d in duplicates]
        return {
            "ok": True,
            "message": f"Deleted {len(duplicates)} duplicate row(s) from the ledger:\n" + "\n".join(lines),
        }

    def handle_command_with_metadata(self, user_input: str) -> dict[str, Any]:
        import calendar as _cal

        # Delete duplicates command
        delete_cmd = self.detect_delete_command(user_input)
        if delete_cmd and delete_cmd.get("action") == "delete_duplicates":
            result = self.delete_duplicate_ledger_rows()
            self.update_short_term_memory(user_input, {"message": result["message"]})
            return {"message": result["message"], "status": self.get_status(), "presentation": None}

        # Budget command check (runs before recurring to avoid false matches)
        budget_cmd = self.detect_budget_command(user_input)
        if budget_cmd:
            if budget_cmd.get("list"):
                budget_data = self.memory.load_budgets()
                count = len(budget_data.get("budgets", []))
                return {"message": f"{count} budget(s) set.", "status": self.get_status(), "presentation": None}
            new_budget = self.budget_engine.set_budget(
                category=budget_cmd["category"],
                amount=budget_cmd["amount"],
                period="monthly",
                business_key=self.memory.current_business_key,
            )
            budget_data = self.memory.load_budgets()
            # Remove existing budget for same category before adding new one
            budget_data["budgets"] = [
                b for b in budget_data["budgets"]
                if b.get("category", "").lower() != budget_cmd["category"].lower()
            ]
            budget_data["budgets"].append(new_budget)
            self.memory.save_budgets(budget_data)
            return {
                "message": f"Budget set — {new_budget['category']} · ${new_budget['amount']:.2f}/month.",
                "status": self.get_status(),
                "presentation": None,
            }

        recurring_cmd = self.detect_recurring_command(user_input)
        if recurring_cmd:
            if recurring_cmd.get("list"):
                schedules = self.recurring.list_schedules()
                msg = f"{len(schedules)} recurring schedule(s) active." if schedules else "No recurring schedules."
                return {"message": msg, "status": self.get_status(), "presentation": None}
            if recurring_cmd.get("cancel"):
                keyword = user_input.lower().replace("cancel", "").replace("recurring", "").strip()
                for s in self.recurring.list_schedules():
                    if keyword in s["description"].lower():
                        self.recurring.cancel_schedule(s["id"])
                        self._save_recurring()
                        return {"message": f"Cancelled recurring: {s['description']}.", "status": self.get_status(), "presentation": None}
                return {"message": "No matching recurring schedule found.", "status": self.get_status(), "presentation": None}
            # Create new schedule
            today = _date.today()
            day = recurring_cmd["day_of_period"]
            freq = recurring_cmd["frequency"]
            last_day = _cal.monthrange(today.year, today.month)[1]
            start = _date(today.year, today.month, min(day, last_day)).isoformat()
            if start < today.isoformat():
                m2 = today.month % 12 + 1
                y2 = today.year if today.month < 12 else today.year + 1
                last2 = _cal.monthrange(y2, m2)[1]
                start = _date(y2, m2, min(day, last2)).isoformat()
            cat = self.categorization.suggest_category(recurring_cmd["description"])
            category = cat["category"] if cat else "Misc"
            freq_full = freq + "ly" if not freq.endswith("ly") else freq
            schedule = self.recurring.create_schedule(
                description=recurring_cmd["description"],
                amount=recurring_cmd["amount"],
                category=category,
                entry_type=recurring_cmd["entry_type"],
                frequency=freq_full,
                day_of_period=day,
                start_date=start,
            )
            self._save_recurring()
            return {
                "message": f"Recurring set — {schedule['description']} · ${schedule['amount']:.2f} · {schedule['entry_type']} · {schedule['frequency']} from {schedule['next_date']}.",
                "status": self.get_status(),
                "presentation": None,
            }

        reconcile_cmd = self.detect_reconcile_command(user_input)
        if reconcile_cmd:
            return {
                "message": "Please use the Reconcile tab in the UI to upload and match bank statements.",
                "status": self.get_status(),
                "presentation": None,
            }

        ar_ap_cmd = self.detect_ar_ap_command(user_input)
        if ar_ap_cmd:
            action = ar_ap_cmd.get("action")
            if action == "add_receivable":
                amount = ar_ap_cmd.get("amount")
                client_vendor = ar_ap_cmd.get("client_vendor")
                if amount is None or client_vendor is None:
                    return {
                        "message": "I need both an amount and a client name to create a receivable. Please specify like: 'Add receivable $500 from ClientName'",
                        "status": self.get_status(),
                        "presentation": None,
                    }
                cat = self.categorization.suggest_category(client_vendor) if client_vendor else None
                category = cat["category"] if cat else "Accounts Receivable"
                due_date = (date.today() + timedelta(days=30)).isoformat()
                result = self.ar_ap_engine.add_receivable(
                    client=client_vendor,
                    amount=amount,
                    due_date=due_date,
                    notes=f"Created via voice command: {user_input}"
                )
                return {
                    "message": f"Created receivable for {client_vendor}: ${amount:.2f} due {due_date}",
                    "status": self.get_status(),
                    "presentation": None,
                }
            elif action == "add_payable":
                amount = ar_ap_cmd.get("amount")
                client_vendor = ar_ap_cmd.get("client_vendor")
                if amount is None or client_vendor is None:
                    return {
                        "message": "I need both an amount and a vendor name to create a payable. Please specify like: 'Add payable $300 for VendorName'",
                        "status": self.get_status(),
                        "presentation": None,
                    }
                cat = self.categorization.suggest_category(client_vendor) if client_vendor else None
                category = cat["category"] if cat else "Accounts Payable"
                due_date = (date.today() + timedelta(days=30)).isoformat()
                result = self.ar_ap_engine.add_payable(
                    vendor=client_vendor,
                    amount=amount,
                    due_date=due_date,
                    notes=f"Created via voice command: {user_input}"
                )
                return {
                    "message": f"Created payable for {client_vendor}: ${amount:.2f} due {due_date}",
                    "status": self.get_status(),
                    "presentation": None,
                }
            elif action == "mark_paid":
                entry_type = ar_ap_cmd.get("entry_type", "receivable")
                data = self.ar_ap_engine.get_ar_ap()
                collection = "receivables" if entry_type == "receivable" else "payables"
                open_entries = [e for e in data[collection] if e["status"] == "open"]
                if not open_entries:
                    return {
                        "message": f"No open {entry_type} entries found to mark as paid.",
                        "status": self.get_status(),
                        "presentation": None,
                    }
                latest_entry = max(open_entries, key=lambda x: x["issue_date"])
                paid_date = date.today().isoformat()
                self.ar_ap_engine.mark_paid(
                    entry_id=latest_entry["id"],
                    entry_type=entry_type,
                    paid_date=paid_date,
                )
                description = (
                    f"Invoice paid: {latest_entry['client_vendor']}"
                    if entry_type == "receivable"
                    else f"Bill paid: {latest_entry['client_vendor']}"
                )
                self.record_structured_transaction(
                    date=paid_date,
                    description=description,
                    category="Accounts Receivable" if entry_type == "receivable" else "Accounts Payable",
                    amount=latest_entry["amount"],
                    entry_type="Income" if entry_type == "receivable" else "Expense",
                    notes=latest_entry.get("notes", ""),
                )
                return {
                    "message": f"Marked {entry_type} '{latest_entry['client_vendor']}' as paid and posted to ledger.",
                    "status": self.get_status(),
                    "presentation": None,
                }
            elif action == "list_ar_ap":
                data = self.ar_ap_engine.get_ar_ap()
                receivables_count = len(data["receivables"])
                payables_count = len(data["payables"])
                overdue_receivables = len([r for r in data["receivables"] if r["days_outstanding"] > 0 and r["status"] == "open"])
                overdue_payables = len([p for p in data["payables"] if p["days_outstanding"] > 0 and p["status"] == "open"])
                return {
                    "message": f"AR/AP Summary: {receivables_count} receivables ({overdue_receivables} overdue), {payables_count} payables ({overdue_payables} overdue)",
                    "status": self.get_status(),
                    "presentation": None,
                }
            elif action == "get_overdue":
                overdue = self.ar_ap_engine.get_overdue_items()
                receivables_count = len(overdue["receivables"])
                payables_count = len(overdue["payables"])
                if receivables_count == 0 and payables_count == 0:
                    return {
                        "message": "No overdue receivables or payables.",
                        "status": self.get_status(),
                        "presentation": None,
                    }
                msg_parts = []
                if receivables_count > 0:
                    msg_parts.append(f"{receivables_count} overdue receivable(s)")
                if payables_count > 0:
                    msg_parts.append(f"{payables_count} overdue payable(s)")
                return {
                    "message": f"Overdue items: {', '.join(msg_parts)}",
                    "status": self.get_status(),
                    "presentation": None,
                }

        tax_cmd = self.detect_tax_command(user_input)
        if tax_cmd:
            action = tax_cmd.get("action")
            if action == "get_tax_estimate":
                # Get net income from ledger
                ledger_rows = self.sheets.read_range(
                    spreadsheet_id=self.memory.get_current_business()["google_sheet_id"],
                    range_name="Ledger!A:G"
                )
                tax_summary = self.tax_engine.compute_tax_summary(ledger_rows)
                return {
                    "message": f"Tax Estimate: Net Income ${tax_summary['net_income']:.2f}, SE Tax ${tax_summary['se_tax']:.2f}, Federal Tax ${tax_summary['federal_tax']:.2f}, Total Tax ${tax_summary['total_tax']:.2f}",
                    "status": self.get_status(),
                    "presentation": None,
                }
            elif action == "get_tax_deadlines":
                current_year = date.today().year
                deadlines = self.tax_engine.get_irs_deadlines(current_year)
                deadline_strs = [f"{d['description']}: {d['deadline']}" for d in deadlines]
                return {
                    "message": f"Tax Deadlines: {', '.join(deadline_strs)}",
                    "status": self.get_status(),
                    "presentation": None,
                }
            elif action == "get_tax_alerts":
                alerts = self.tax_engine.get_upcoming_alerts()
                if not alerts:
                    return {
                        "message": "No upcoming tax deadlines in the next 30 days.",
                        "status": self.get_status(),
                        "presentation": None,
                    }
                alert_strs = [f"{a['description']}: {a['deadline']} ({a['days_until']} days)" for a in alerts]
                return {
                    "message": f"Upcoming Tax Alerts: {', '.join(alert_strs)}",
                    "status": self.get_status(),
                    "presentation": None,
                }

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
