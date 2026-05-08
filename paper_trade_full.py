"""
Version 1 — Paper Trading Full
--------------------------------
Analysts : market, news, fundamentals  (no social/sentiment)
News data: Alpha Vantage (NEWS_SENTIMENT) if ALPHA_VANTAGE_API_KEY is set,
           falls back to yfinance news automatically.
Price    : yfinance (real-time intraday)
Rate     : FRED API (DFF series)
Schedule : every 30 minutes, 9:30 AM – 4:00 PM ET

Usage:
    source venv/bin/activate
    python paper_trade_full.py
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tradingagents"))

from dotenv import load_dotenv
load_dotenv()

from config import (
    LLM_PROVIDER, DEEP_THINK_LLM, QUICK_THINK_LLM,
    DATA_VENDORS, PAPER_FULL_STATE_FILE, SAVINGS_RATE,
)
from portfolio import Portfolio
from runner import run_scheduler, get_spy_price
from llm_logger import LLMLogger
from portfolio_context_patch import apply_portfolio_context_patch
from memory_store import load_memories
from rich.console import Console

console = Console()


def build_graph(logger: LLMLogger):
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    from tradingagents.default_config import DEFAULT_CONFIG

    cfg = DEFAULT_CONFIG.copy()
    cfg["llm_provider"]            = LLM_PROVIDER
    cfg["deep_think_llm"]          = DEEP_THINK_LLM
    cfg["quick_think_llm"]         = QUICK_THINK_LLM
    cfg["max_debate_rounds"]       = 1
    cfg["max_risk_discuss_rounds"] = 1
    cfg["data_vendors"]            = DATA_VENDORS
    cfg["backend_url"]             = None   # clear OpenAI default — Anthropic uses its own endpoint

    return TradingAgentsGraph(
        selected_analysts=["market", "news", "fundamentals"],
        debug=False,
        config=cfg,
        callbacks=[logger],
    )


if __name__ == "__main__":
    console.rule("[bold blue]Paper Trading — FULL (market + news + fundamentals)")
    console.print(f"  LLM      : {LLM_PROVIDER} / {DEEP_THINK_LLM}")
    console.print(f"  News     : {DATA_VENDORS['news_data']}")
    console.print(f"  Cash rate: {SAVINGS_RATE*100:.2f}% APY (FRED DFF)")
    console.print(f"  LLM log  : data/llm_calls.csv\n")

    logger    = LLMLogger()
    portfolio = Portfolio(PAPER_FULL_STATE_FILE)
    apply_portfolio_context_patch(portfolio)
    ta        = build_graph(logger)

    n = load_memories(ta)
    if n:
        console.print(f"  Memories : {n} past lessons loaded from data/memory/\n")
    else:
        console.print(f"  Memories : none yet (first run or no closed positions)\n")

    run_scheduler(ta, portfolio, label="FULL", logger=logger)
