"""
process_data.py — Daily data processing pipeline.

Reads data/llm_calls.csv, runs all registered processing steps,
and writes a new dated file: data/llm_calls_processed_YYYY-MM-DD.csv.

Scheduled to run at 3 PM PT on weekdays (after market close).
Add new processing steps as functions and register them in PIPELINE.

Usage:
    python process_data.py
    python process_data.py --date 2026-05-06   # process a specific date's output
"""

import csv
import os
import sys
from datetime import date

csv.field_size_limit(10_000_000)

# ── Paths ─────────────────────────────────────────────────────────────────────

BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
DATA_DIR  = os.path.join(BASE_DIR, "data")
INPUT_CSV = os.path.join(DATA_DIR, "llm_calls.csv")


# ── Step 1: Agent classification ──────────────────────────────────────────────

# Ordered from most specific to least specific.
# Each entry: (label, list of substrings to match anywhere in the prompt)
AGENT_PATTERNS = [
    # Portfolio manager roles (Sonnet — check these first, highly specific)
    ("debate_facilitator",       ["portfolio manager and debate facilitator"]),
    ("portfolio_manager",        ["As the Portfolio Manager, synthesize the risk"]),
    ("signal_processor",         ["extracts the trading decision from analyst reports"]),

    # Risk analysts
    ("risk_analyst_aggressive",  ["As the Aggressive Risk Analyst"]),
    ("risk_analyst_conservative",["As the Conservative Risk Analyst"]),
    ("risk_analyst_neutral",     ["As the Neutral Risk Analyst"]),

    # Researchers
    ("bull_researcher",          ["You are a Bull Analyst"]),
    ("bear_researcher",          ["You are a Bear Analyst"]),

    # Trader
    ("trader",                   ["You are a trading agent analyzing market data"]),

    # Analysts — distinguished by tool names in the prompt
    ("market_analyst",           ["tools: get_stock_data, get_indicators"]),
    ("news_analyst",             ["tools: get_news, get_global_news"]),
    ("fundamentals_analyst",     ["tools: get_fundamentals, get_balance_sheet"]),
]


def _classify_agent(prompt: str) -> str:
    for label, patterns in AGENT_PATTERNS:
        for pattern in patterns:
            if pattern in prompt:
                return label
    return "unknown"


def add_agent_labels(rows: list[dict]) -> list[dict]:
    """Add/update the 'agent' column via prompt pattern matching."""
    filled = 0
    for row in rows:
        if not row.get("agent"):
            row["agent"] = _classify_agent(row.get("prompt", ""))
            filled += 1
    print(f"  [add_agent_labels] labelled {filled} rows")
    return rows


# ── Pipeline registry ─────────────────────────────────────────────────────────

# Each entry: (description, function(rows) -> rows)
# Steps run in order; each receives and returns the full list of row dicts.
PIPELINE = [
    ("Add agent labels via prompt pattern matching", add_agent_labels),
]


# ── Runner ────────────────────────────────────────────────────────────────────

def run(run_date: str | None = None) -> None:
    if run_date is None:
        run_date = date.today().isoformat()

    output_csv = os.path.join(DATA_DIR, f"llm_calls_processed_{run_date}.csv")

    print(f"process_data.py — {run_date}")
    print(f"  Input : {INPUT_CSV}")
    print(f"  Output: {output_csv}")

    # ── Read ──────────────────────────────────────────────────────────────────
    if not os.path.exists(INPUT_CSV):
        print(f"  ERROR: {INPUT_CSV} not found — nothing to process.")
        sys.exit(1)

    with open(INPUT_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        original_fields = reader.fieldnames or []
        rows = list(reader)

    print(f"  Read {len(rows)} rows, {len(original_fields)} columns")

    # ── Run pipeline ──────────────────────────────────────────────────────────
    for description, fn in PIPELINE:
        print(f"  Running: {description}")
        rows = fn(rows)

    # ── Determine output columns (original + any new ones added by pipeline) ──
    all_fields = list(original_fields)
    for row in rows:
        for key in row:
            if key not in all_fields:
                all_fields.append(key)

    # ── Write ─────────────────────────────────────────────────────────────────
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=all_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(f"  Wrote {len(rows)} rows with columns: {all_fields}")
    print("Done.")


if __name__ == "__main__":
    arg_date = None
    if "--date" in sys.argv:
        idx = sys.argv.index("--date")
        arg_date = sys.argv[idx + 1]
    run(arg_date)
