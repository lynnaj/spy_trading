"""
LLM call logger — captures every query and response from every agent.

Hooks into LangChain's callback system via TradingAgentsGraph(callbacks=[LLMLogger(...)]).
Writes one row per LLM call to data/llm_calls.csv.

CSV columns:
    timestamp        UTC ISO datetime of the call
    slot             30-min trading slot  e.g. "2026-05-05 09:30"
    run_id           UUID tying the start and end events together
    model            Model name  e.g. "claude-sonnet-4-6"
    prompt           Full prompt text sent to the model
    response         Full response text returned
    prompt_tokens    Input token count (when available)
    completion_tokens Output token count (when available)
    duration_ms      Wall-clock time for the call
"""

import csv
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import BaseMessage
from langchain_core.outputs import LLMResult

from config import DATA_DIR

LOG_FILE = os.path.join(DATA_DIR, "llm_calls.csv")

HEADERS = [
    "timestamp",
    "slot",
    "run_id",
    "model",
    "prompt",
    "response",
    "prompt_tokens",
    "completion_tokens",
    "duration_ms",
]


def _messages_to_text(messages: List[List[BaseMessage]]) -> str:
    """Flatten LangChain message batches into a single readable string."""
    parts = []
    for batch in messages:
        for msg in batch:
            role = msg.__class__.__name__.replace("Message", "").upper()
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            parts.append(f"[{role}]\n{content}")
    return "\n\n".join(parts)


def _response_to_text(response: LLMResult) -> str:
    """Extract text from LLMResult generations."""
    parts = []
    for batch in response.generations:
        for gen in batch:
            if hasattr(gen, "message") and hasattr(gen.message, "content"):
                content = gen.message.content
            elif hasattr(gen, "text"):
                content = gen.text
            else:
                content = str(gen)
            if isinstance(content, list):
                content = " ".join(
                    block.get("text", "") if isinstance(block, dict) else str(block)
                    for block in content
                )
            parts.append(content)
    return "\n\n".join(parts)


def _token_counts(response: LLMResult) -> tuple[Optional[int], Optional[int]]:
    """Extract prompt and completion token counts from LLMResult if available."""
    usage = (response.llm_output or {}).get("token_usage") or \
            (response.llm_output or {}).get("usage") or {}
    prompt     = usage.get("prompt_tokens") or usage.get("input_tokens")
    completion = usage.get("completion_tokens") or usage.get("output_tokens")
    return prompt, completion


class LLMLogger(BaseCallbackHandler):
    """
    LangChain callback handler that logs every LLM query and response to CSV.

    Usage:
        logger = LLMLogger(slot="2026-05-05 09:30")
        ta = TradingAgentsGraph(callbacks=[logger], ...)
        logger.slot = current_slot()   # update each cycle
    """

    def __init__(self, slot: str = ""):
        super().__init__()
        self.slot = slot
        self._pending: Dict[str, Dict] = {}  # run_id → {start_time, model, prompt}
        self._init_file()

    def _init_file(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        if not os.path.exists(LOG_FILE):
            with open(LOG_FILE, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(HEADERS)

    def _append_row(self, row: dict):
        with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=HEADERS)
            writer.writerow(row)

    # ── LangChain callback hooks ──────────────────────────────────────────────

    def on_chat_model_start(
        self,
        serialized: Dict[str, Any],
        messages: List[List[BaseMessage]],
        *,
        run_id: UUID,
        **kwargs,
    ) -> None:
        model = (
            serialized.get("kwargs", {}).get("model")
            or serialized.get("kwargs", {}).get("model_name")
            or serialized.get("name", "unknown")
        )
        self._pending[str(run_id)] = {
            "start_time": time.monotonic(),
            "timestamp":  datetime.now(timezone.utc).isoformat(),
            "model":      model,
            "prompt":     _messages_to_text(messages),
        }

    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        **kwargs,
    ) -> None:
        key = str(run_id)
        pending = self._pending.pop(key, None)
        if pending is None:
            return

        duration_ms    = int((time.monotonic() - pending["start_time"]) * 1000)
        prompt_tok, completion_tok = _token_counts(response)

        self._append_row({
            "timestamp":         pending["timestamp"],
            "slot":              self.slot,
            "run_id":            key,
            "model":             pending["model"],
            "prompt":            pending["prompt"],
            "response":          _response_to_text(response),
            "prompt_tokens":     prompt_tok or "",
            "completion_tokens": completion_tok or "",
            "duration_ms":       duration_ms,
        })

    def on_llm_error(self, error: Exception, *, run_id: UUID, **kwargs) -> None:
        self._pending.pop(str(run_id), None)
