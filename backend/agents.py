"""Five Campus Customs agents. Shop facts come only from the MCP tools."""

from __future__ import annotations

import os
import re
import sys
import threading
from pathlib import Path

os.environ["PYDANTIC_AI_NO_BANNER"] = "1"

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from mcp_server import tools

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

PROMPT_DIR = Path(__file__).resolve().parent / "prompts"
MODEL_NAME = "gpt-6-luna"
MAX_TOKENS = 1200
_LLM_OK: bool | None = None


def load_prompt(name: str) -> str:
    return (PROMPT_DIR / f"{name}.md").read_text()


def _model() -> OpenAIChatModel:
    key = os.getenv("PORTKEY_API_KEY", "")
    return OpenAIChatModel(
        MODEL_NAME,
        provider=OpenAIProvider(base_url="https://api.portkey.ai/v1", api_key=key or "missing"),
    )


def build_agents() -> dict[str, Agent]:
    return {
        name: Agent(
            _model(),
            name=name,
            system_prompt=load_prompt(name),
            model_settings={"max_tokens": MAX_TOKENS},
            defer_model_check=True,
        )
        for name in ("boss", "inventory", "accounting", "facilities", "customer_service")
    }


AGENTS = build_agents()


def _keeps_shop_facts(text: str, fallback: str) -> bool:
    lowered = text.lower()
    if any(phrase in lowered for phrase in ("can't", "cannot", "no facts", "no campus", "no details")):
        return False
    for amount in re.findall(r"\$\d[\d,]*(?:\.\d+)?", fallback):
        if amount not in text:
            return False
    for token in re.findall(r"\b(?:CC-[A-Z0-9-]+|\d{4}-\d{2}-\d{2})\b", fallback):
        if token not in text:
            return False
    return True


def speak(agent_name: str, facts: str, fallback: str) -> str:
    """Ask gpt-6-luna to phrase a note. Keep the shop-rule sentence if the reply drops a fact."""
    global _LLM_OK
    if not os.getenv("PORTKEY_API_KEY") or _LLM_OK is False:
        return fallback
    prompt = (
        "Rewrite the note in two short sentences. Keep every number, name, sku, and date the same. "
        "Do not add facts.\n"
        f"Note: {fallback}\nFacts: {facts}"
    )
    box: dict[str, str] = {}

    def _call() -> None:
        try:
            result = AGENTS[agent_name].run_sync(prompt)
            box["text"] = str(result.output).strip()
        except Exception:
            box["text"] = ""

    worker = threading.Thread(target=_call, daemon=True)
    try:
        worker.start()
        worker.join(8)
    except Exception:
        _LLM_OK = False
        return fallback
    text = box.get("text", "")
    if worker.is_alive() or not text or len(text) > 900 or not _keeps_shop_facts(text, fallback):
        _LLM_OK = False
        return fallback
    _LLM_OK = True
    return text


def toolbelt():
    """The only shop-data functions the agents may use."""
    return tools
