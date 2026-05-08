"""Central configuration for the SPY trading agent system."""

import os
from dotenv import load_dotenv

load_dotenv()

# ── Portfolio ─────────────────────────────────────────────────────────────────
STARTING_BALANCE: float = float(os.getenv("STARTING_BALANCE", 100_000))

# Savings rate: use SAVINGS_RATE env var to override, otherwise fetch live from FRED (DFF series).
_env_rate = os.getenv("SAVINGS_RATE")
if _env_rate:
    SAVINGS_RATE: float = float(_env_rate)
else:
    from rates import get_savings_rate
    SAVINGS_RATE: float = get_savings_rate(verbose=True)

# ── Ticker ────────────────────────────────────────────────────────────────────
TICKER = "SPY"

# ── LLM ──────────────────────────────────────────────────────────────────────
LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "openai")

_DEFAULTS = {
    "openai":    ("gpt-4o", "gpt-4o-mini"),
    "anthropic": ("claude-sonnet-4-6", "claude-haiku-4-5-20251001"),
    "google":    ("gemini-2.0-flash-thinking-exp", "gemini-2.0-flash"),
    "xai":       ("grok-3", "grok-3-mini"),
    "deepseek":  ("deepseek-reasoner", "deepseek-chat"),
}

_deep, _quick = _DEFAULTS.get(LLM_PROVIDER, ("gpt-4o", "gpt-4o-mini"))
DEEP_THINK_LLM: str = os.getenv("DEEP_THINK_LLM") or _deep
QUICK_THINK_LLM: str = os.getenv("QUICK_THINK_LLM") or _quick

# ── Data vendors ──────────────────────────────────────────────────────────────
# Use Alpha Vantage for news if the key is present; fall back to yfinance.
# Price, technical indicators, and fundamentals always use yfinance (no key needed,
# unlimited requests, and the free Alpha Vantage tier is only 25 req/day).
_av_key = os.getenv("ALPHA_VANTAGE_API_KEY", "")
NEWS_VENDOR = "alpha_vantage" if _av_key else "yfinance"

DATA_VENDORS = {
    "core_stock_apis":      "yfinance",
    "technical_indicators": "yfinance",
    "fundamental_data":     "yfinance",
    "news_data":            NEWS_VENDOR,
}

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
TRADINGAGENTS_DIR = os.path.join(os.path.dirname(BASE_DIR), "tradingagents")

PAPER_FULL_STATE_FILE = os.path.join(DATA_DIR, "paper_full_portfolio.json")
PAPER_LEAN_STATE_FILE = os.path.join(DATA_DIR, "paper_lean_portfolio.json")

os.makedirs(DATA_DIR, exist_ok=True)

# ── Decision mapping ──────────────────────────────────────────────────────────
# BUY / OVERWEIGHT   → invest all cash into SPY
# SELL / UNDERWEIGHT → liquidate all SPY to cash
# HOLD               → no action
BUY_SIGNALS = {"BUY", "OVERWEIGHT"}
SELL_SIGNALS = {"SELL", "UNDERWEIGHT"}
