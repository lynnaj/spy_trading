"""
memory_store.py — Persist and restore TradingAgents BM25 memory objects.

Each of the 5 per-agent memories is serialized to its own JSON file under
data/memory/. The BM25 index is rebuilt automatically on load via add_situations().

Usage:
    load_memories(ta)   # call once after build_graph(), before first propagate()
    save_memories(ta)   # call after reflect_and_remember()
"""

import json
import os

from config import DATA_DIR

MEMORY_DIR = os.path.join(DATA_DIR, "memory")

MEMORY_ATTRS = [
    ("bull_memory",               "bull_memory.json"),
    ("bear_memory",               "bear_memory.json"),
    ("trader_memory",             "trader_memory.json"),
    ("invest_judge_memory",       "invest_judge_memory.json"),
    ("portfolio_manager_memory",  "portfolio_manager_memory.json"),
]


def save_memories(ta) -> None:
    """Serialize all 5 agent memory objects to JSON files in data/memory/."""
    os.makedirs(MEMORY_DIR, exist_ok=True)
    for attr, filename in MEMORY_ATTRS:
        mem  = getattr(ta, attr)
        path = os.path.join(MEMORY_DIR, filename)
        with open(path, "w") as f:
            json.dump(
                {"documents": mem.documents, "recommendations": mem.recommendations},
                f,
                indent=2,
            )


def load_memories(ta) -> int:
    """
    Load all 5 agent memory objects from JSON files.
    Skips files that don't exist yet (first run).
    Returns the total number of lessons loaded across all agents.
    """
    total = 0
    for attr, filename in MEMORY_ATTRS:
        path = os.path.join(MEMORY_DIR, filename)
        if not os.path.exists(path):
            continue
        with open(path) as f:
            data = json.load(f)
        docs = data.get("documents", [])
        recs = data.get("recommendations", [])
        if docs:
            getattr(ta, attr).add_situations(list(zip(docs, recs)))
            total += len(docs)
    return total
