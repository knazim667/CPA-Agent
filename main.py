from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any

import requests
import speech_recognition as sr

from core.ollama_client import OllamaClient
from memory_manager import MemoryManager
from skills import GoogleDocsManager, GoogleSheetsManager


ROOT_DIR = Path(__file__).resolve().parent
PERSONA_DIR = ROOT_DIR / "persona"
SYSTEM_PROMPT_PATH = PERSONA_DIR / "system_prompt.md"
CUSTOM_RULES_PATH = PERSONA_DIR / "custom_rules.json"


class CPAAgent:
    def __init__(self) -> None:
        self.memory = MemoryManager(ROOT_DIR / "memory")
        self.ollama = OllamaClient()
        self.sheets = GoogleSheetsManager()
        self.docs = GoogleDocsManager()
        self.recognizer = sr.Recognizer()
        self.recognizer.pause_threshold = 0.8
        self.wake_words = ("hey cpa-agent", "hey cpa agent", "cpa-agent", "cpa agent")
        self.input_mode = self._determine_input_mode()
        self._load_persona_assets()
        self.ensure_business_workspace_assets()

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
            f"{short_term_context}"
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
            result = self.sheets.append_ledger_row(
                spreadsheet_id=profile["google_sheet_id"],
                worksheet_name=parameters.get("worksheet_name", "Ledger"),
                row_values=parameters.get("row_values", []),
            )
            return {"status": "success", "message": "Transaction recorded.", "details": result}

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
            self.sheets.ensure_ledger_sheet(
                spreadsheet_id=target_sheet_id,
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
        return final_message

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
