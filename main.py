"""CPA-Agent — thin CPAAgent orchestrator. All domain logic lives in core/."""

import json
import os
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

import speech_recognition as sr
from dotenv import load_dotenv

load_dotenv()

from core.model_client import get_model_client
from core.transaction_recorder import (
    record_structured_transaction as _record_structured_transaction,
    record_bulk_transactions as _record_bulk_transactions,
    draft_document_transactions as _draft_document_transactions,
)
from core.ai_engine import build_messages as _build_messages, extract_action_plan as _extract_action_plan
from core.ledger_utils import LEDGER_HEADERS as _LEDGER_HEADERS, normalize_row as _normalize_row, safe_float as _safe_float
from core.action_executor import execute_action as _execute_action
from core.status_builder import get_dashboard_snapshot as _get_dashboard_snapshot, build_status as _build_status, get_model_status as _get_model_status
from core.presentation_builder import build_presentation as _build_presentation_fn, clean_response_text as _clean_response_text
from core.command_handler import handle_command as _handle_command, handle_command_with_metadata as _handle_command_with_metadata
from core.workspace_manager import ensure_business_workspace_assets as _ensure_workspace
from memory_manager import MemoryManager
from skills import (
    GoogleDocsManager, GoogleSheetsManager, KnowledgeManager,
    CategorizationEngine, RecurringEngine, FinancialStatements,
    BudgetEngine, ReconciliationEngine, ARAPEngine, TaxEngine,
)

ROOT_DIR = Path(__file__).resolve().parent
PERSONA_DIR = ROOT_DIR / "persona"
SYSTEM_PROMPT_PATH = PERSONA_DIR / "system_prompt.md"
CUSTOM_RULES_PATH = PERSONA_DIR / "custom_rules.json"


class CPAAgent:
    """Thin orchestrator — delegates all domain logic to core/ modules."""

    LEDGER_HEADERS = _LEDGER_HEADERS
    _STATUS_CACHE_TTL = 2.0

    def __init__(self) -> None:
        self.memory = MemoryManager(ROOT_DIR / "memory")
        self.reasoning_mode = self._normalize_reasoning_mode(
            os.getenv("CPA_AGENT_REASONING_MODE", "fast")
        )
        self._refresh_model_clients()
        self.sheets = GoogleSheetsManager()
        self.docs = GoogleDocsManager()
        self.knowledge = KnowledgeManager()
        self.categorization = CategorizationEngine(rules_data=self.memory.load_category_rules())
        self.recurring = RecurringEngine(recurring_data=self.memory.load_recurring())
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
                pass
        self.recognizer = sr.Recognizer()
        self.recognizer.pause_threshold = 0.8
        self.wake_words = ("hey cpa-agent", "hey cpa agent", "cpa-agent", "cpa agent")
        self.input_mode = self._determine_input_mode()
        self.workspace_boot_error: str | None = None
        self._workbook_ready: set[str] = set()
        self.custom_rules_path = CUSTOM_RULES_PATH
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
        safe_message = os.fsencode(message)
        subprocess = __import__("subprocess")
        subprocess.run(f"say {safe_message.decode()}", shell=True, check=False)

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

    @lru_cache(maxsize=128)
    def run_reasoning_cached(self, user_input: str) -> dict[str, Any]:
        self.refresh_rules()
        messages = _build_messages(
            user_input,
            system_prompt=self.system_prompt,
            custom_rules=self.custom_rules,
            memory=self.memory,
            ar_ap_engine=self.ar_ap_engine,
        )
        return _extract_action_plan(self.model_client.chat(messages))

    def run_reasoning(self, user_input: str) -> dict[str, Any]:
        return self.run_reasoning_cached(user_input)

    def execute_action(self, plan: dict[str, Any], user_input: str) -> dict[str, Any]:
        result = _execute_action(
            plan, user_input,
            sheets=self.sheets, docs=self.docs, memory=self.memory,
            ensure_workspace=self.ensure_business_workspace_assets,
        )
        self.workspace_boot_error = result.get("details", {}).get("workspace_boot_error")
        return result

    def record_structured_transaction(self, *, date: str, description: str, category: str,
                                      amount: float, entry_type: str, reference: str = "",
                                      notes: str = "") -> dict[str, Any]:
        profile = self.ensure_business_workspace_assets()
        return _record_structured_transaction(
            date=date, description=description, category=category, amount=amount,
            entry_type=entry_type, reference=reference, notes=notes,
            profile=profile, sheets=self.sheets, memory=self.memory,
            reflection_client=self.reflection_client, custom_rules=self.custom_rules,
        )

    def record_bulk_transactions(self, rows: list, *, source_name: str = "", source_note: str = "") -> dict[str, Any]:
        profile = self.ensure_business_workspace_assets()
        return _record_bulk_transactions(
            rows, source_name=source_name, source_note=source_note,
            profile=profile, sheets=self.sheets, memory=self.memory,
            reflection_client=self.reflection_client, custom_rules=self.custom_rules,
        )

    def draft_document_transactions(self, *, file_name: str, document_text: str, instruction: str = "") -> dict[str, Any]:
        return _draft_document_transactions(
            file_name=file_name, document_text=document_text, instruction=instruction,
            model_client=self.model_client, memory=self.memory,
        )

    def list_businesses(self) -> list[dict[str, str]]:
        return [
            {"key": key, "business_name": self.memory.load_business_profile(key)["business_name"]}
            for key in self.memory.list_business_keys()
        ]

    def get_dashboard_snapshot(self) -> dict[str, Any]:
        return _get_dashboard_snapshot(self.memory, self.sheets, self.LEDGER_HEADERS)

    def get_status(self) -> dict[str, Any]:
        now = time.monotonic()
        if hasattr(self, "_status_cache"):
            ts, cached = self._status_cache
            if now - ts < self._STATUS_CACHE_TTL:
                return cached
        result = _build_status(self)
        self._status_cache = (now, result)
        return result

    def get_model_status(self) -> dict[str, str]:
        return _get_model_status(self.reasoning_mode)

    @staticmethod
    def _normalize_row(row: list) -> list:
        return _normalize_row(row)

    @staticmethod
    def _safe_float(value: Any) -> float:
        return _safe_float(value)

    def _build_presentation(self, outcome: dict[str, Any], status: dict[str, Any], message: str) -> dict[str, Any] | None:
        return _build_presentation_fn(outcome, status, message, self.LEDGER_HEADERS)

    def ensure_business_workspace_assets(self) -> dict[str, Any]:
        return _ensure_workspace(self.memory, self.sheets, self.docs, self._workbook_ready)

    def handle_command(self, user_input: str) -> str:
        return _handle_command(user_input, self)

    def handle_command_with_metadata(self, user_input: str) -> dict[str, Any]:
        return _handle_command_with_metadata(user_input, self)

    def run(self) -> None:
        import requests as _requests
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
            except _requests.RequestException as exc:
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
