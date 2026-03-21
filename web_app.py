from __future__ import annotations

from pathlib import Path
from threading import Lock
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from main import CPAAgent


ROOT_DIR = Path(__file__).resolve().parent
UI_DIR = ROOT_DIR / "ui"

app = FastAPI(title="CPA-Agent UI")
app.mount("/ui", StaticFiles(directory=UI_DIR), name="ui")

agent = CPAAgent()
agent_lock = Lock()


class MessageRequest(BaseModel):
    message: str


class BusinessSwitchRequest(BaseModel):
    business_name: str


class ModelModeRequest(BaseModel):
    mode: str


class TransactionRequest(BaseModel):
    date: str
    description: str
    category: str
    amount: float
    entry_type: str
    reference: str = ""
    notes: str = ""


@app.get("/")
def index() -> FileResponse:
    return FileResponse(UI_DIR / "index.html")


@app.get("/api/status")
def get_status() -> dict[str, Any]:
    with agent_lock:
        return agent.get_status()


@app.post("/api/message")
def send_message(payload: MessageRequest) -> dict[str, Any]:
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    with agent_lock:
        try:
            response = agent.handle_command_with_metadata(message)
            return {
                "ok": True,
                "message": response["message"],
                "status": response["status"],
                "presentation": response["presentation"],
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "message": f"I could not complete that safely: {exc}",
                "status": agent.get_status(),
                "presentation": None,
            }


@app.post("/api/switch-business")
def switch_business(payload: BusinessSwitchRequest) -> dict[str, Any]:
    business_name = payload.business_name.strip()
    if not business_name:
        raise HTTPException(status_code=400, detail="Business name cannot be empty.")

    with agent_lock:
        try:
            profile = agent.memory.switch_business(business_name)
            agent.workspace_boot_error = None
            try:
                profile = agent.ensure_business_workspace_assets()
            except Exception as exc:  # noqa: BLE001
                agent.workspace_boot_error = str(exc)
            return {
                "ok": True,
                "message": f"Switched to {profile['business_name']}.",
                "status": agent.get_status(),
            }
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/model-mode")
def set_model_mode(payload: ModelModeRequest) -> dict[str, Any]:
    mode = payload.mode.strip().lower()
    if mode not in {"fast", "quality"}:
        raise HTTPException(status_code=400, detail="Mode must be 'fast' or 'quality'.")

    with agent_lock:
        config = agent.set_reasoning_mode(mode)
        return {
            "ok": True,
            "message": (
                f"Reasoning mode set to {config['reasoning_mode']}. "
                f"Primary model: {config['reasoning_model']}. "
                f"Reflection model: {config['reflection_model']}."
            ),
            "status": agent.get_status(),
        }


@app.post("/api/record-transaction")
def record_transaction(payload: TransactionRequest) -> dict[str, Any]:
    with agent_lock:
        try:
            result = agent.record_structured_transaction(
                date=payload.date,
                description=payload.description,
                category=payload.category,
                amount=payload.amount,
                entry_type=payload.entry_type,
                reference=payload.reference,
                notes=payload.notes,
            )
            agent.workspace_boot_error = None
        except Exception as exc:  # noqa: BLE001
            agent.workspace_boot_error = str(exc)
            result = {
                "ok": False,
                "message": f"I could not record that transaction safely: {exc}",
            }
        return {
            "ok": result["ok"],
            "message": result["message"],
            "status": agent.get_status(),
            "presentation": agent._build_presentation(
                {
                    "details": result.get("details", {}),
                },
                agent.get_status(),
                result["message"],
            ),
        }


def main() -> int:
    import uvicorn

    uvicorn.run("web_app:app", host="127.0.0.1", port=8000, reload=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
