"""Board events, pending human approvals, and the append-only audit trail."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output"
AUDIT_PATH = OUTPUT / "audit_trail.json"
STATE_PATH = OUTPUT / "runtime_state.json"
_LOCK = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read(path: Path, default):
    if not path.exists():
        return default
    text = path.read_text().strip()
    if not text:
        return default
    return json.loads(text)


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))


def load_state() -> dict:
    state = _read(STATE_PATH, {"events": [], "pending": {}, "summaries": {}})
    state.setdefault("events", [])
    state.setdefault("pending", {})
    state.setdefault("summaries", {})
    return state


def save_state(state: dict) -> None:
    _write(STATE_PATH, state)


def reset_board() -> None:
    """Clear the on-screen log and pending pays. Do not touch audit_trail.json."""
    save_state({"events": [], "pending": {}, "summaries": {}})


def append_step(
    ticket_id: int,
    agent: str,
    text: str,
    tool: str | None = None,
    tool_input: dict | None = None,
    tool_output=None,
) -> dict:
    entry = {
        "ts": _now(),
        "ticket_id": ticket_id,
        "agent": agent,
        "text": text,
        "tool": tool,
        "tool_input": tool_input,
        "tool_output": tool_output,
        "model": "gpt-6-luna",
    }
    with _LOCK:
        state = load_state()
        state["events"].append(entry)
        bucket = state["summaries"].setdefault(str(ticket_id), {})
        bucket.setdefault(agent, []).append(text)
        save_state(state)
        audit = _read(AUDIT_PATH, [])
        audit.append(entry)
        _write(AUDIT_PATH, audit)
    return entry


def set_pending(ticket_id: int, proposal: dict) -> None:
    with _LOCK:
        state = load_state()
        state["pending"][str(ticket_id)] = proposal
        save_state(state)


def pop_pending(ticket_id: int) -> dict | None:
    with _LOCK:
        state = load_state()
        proposal = state["pending"].pop(str(ticket_id), None)
        save_state(state)
        return proposal


def get_pending(ticket_id: int) -> dict | None:
    return load_state()["pending"].get(str(ticket_id))


def events_for(ticket_id: int | None = None) -> list[dict]:
    events = load_state()["events"]
    if ticket_id is None:
        return events
    return [event for event in events if event["ticket_id"] == ticket_id]


def summaries_for(ticket_id: int) -> dict:
    return load_state()["summaries"].get(str(ticket_id), {})
