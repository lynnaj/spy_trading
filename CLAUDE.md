# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose

This project wraps the [TradingAgents](https://github.com/tauricresearch/tradingagents) multi-agent LLM framework to track AI trading decisions on a single ticker: **SPY**. Both versions start with **$100,000** and apply the live Federal Funds Rate (fetched from FRED) to any uninvested cash.

Two operational versions, both running every 30 minutes from 9:30 AM – 4:00 PM ET:
- **Version 1 — Paper Trading Full** (`paper_trade_full.py`): market + news + fundamentals analysts. News sourced from Alpha Vantage (falls back to yfinance if key absent). No social/sentiment analyst.
- **Version 2 — Paper Trading Lean** (`paper_trade_lean.py`): market + fundamentals analysts only. No news, no sentiment. Lowest cost per run.

| | Version 1 — Paper Full | Version 2 — Paper Lean |
|---|---|---|
| Price / technicals | Real-time ✓ | Real-time ✓ |
| Fundamentals | Real-time ✓ | Real-time ✓ |
| News (Alpha Vantage) | Real-time ✓ | Disabled |
| Social / sentiment | Disabled | Disabled |
| AI analysts used | `market`, `news`, `fundamentals` | `market`, `fundamentals` |
| Schedule | Every 30 min, market hours | Every 30 min, market hours |

## Tech Stack

| Layer | Tech |
|---|---|
| Python runtime | 3.10 (venv at `venv/`, system path `/opt/homebrew/bin/python3.10`) |
| AI decision engine | `tradingagents` package at `../tradingagents/` (LangGraph multi-agent graph) |
| Market data | `yfinance` — no API key required for price or fundamentals |
| Interest rate | FRED API (`DFF` series) — free key required |
| LLM providers | OpenAI (default), Anthropic, Google, xAI, DeepSeek — one key required |
| Portfolio state | JSON files in `data/` (`paper_full_portfolio.json`, `paper_lean_portfolio.json`) |

## Setup

```bash
cd ~/Github/spy_trading

# Activate venv (Python 3.10 required by tradingagents)
source venv/bin/activate

# Install dependencies
pip install -e ../tradingagents/   # installs tradingagents + all its deps
pip install python-dotenv rich     # spy_trading extras

# Configure API keys
cp .env.example .env
# Edit .env — set FRED_API_KEY, LLM_PROVIDER, and the matching LLM API key
```

## Setup (run once)

```bash
cd ~/Github/spy_trading
chmod +x setup.sh && ./setup.sh    # installs all dependencies into venv
```

## Running

```bash
source venv/bin/activate

# Version 1: market + news + fundamentals — runs every 30 min during market hours
python paper_trade_full.py         # leave running all day; exits at 4:00 PM ET

# Version 2: market + fundamentals only (build in progress)
# python paper_trade_lean.py

# View performance report
python report.py                   # summary
python report.py --trades          # full trade history

# After market close — run daily data processing (adds agent labels to LLM call log)
python process_data.py             # writes data/llm_calls_processed_YYYY-MM-DD.csv
python process_data.py --date 2026-05-06   # reprocess a specific date
```

## External Data Sources

| Call | What it does | Account required? |
|---|---|---|
| `yfinance` → Yahoo Finance | Price, technical indicators, fundamentals | No — free public data feed |
| Alpha Vantage (`NEWS_SENTIMENT`) | News articles with built-in sentiment scores; true date-range queries | Free key (25 req/day) — falls back to yfinance news if key absent |
| Reddit API (PRAW) | Real crowd sentiment: posts + scores + upvote ratios from r/wallstreetbets, r/investing, r/SPY, r/stocks, r/options | Free OAuth app at reddit.com/prefs/apps — sentiment skipped if key absent |
| LLM API (OpenAI/Anthropic/etc.) | Runs the AI decision pipeline | API key only — no brokerage signup |
| FRED API (`DFF` series) | Effective Federal Funds Rate daily; applied as cash savings rate | Free key at fred.stlouisfed.org — falls back to 4.21% if key absent |

## Architecture

### Decision pipeline (TradingAgents)

`TradingAgentsGraph.propagate(ticker, date)` runs a 4-phase LangGraph pipeline:

1. **Analysts** (parallel): market (8 technical indicators), news, social sentiment, fundamentals — each writes a report.
2. **Researchers**: bull and bear agents debate via the analyst reports → Research Manager synthesizes an investment plan.
3. **Trader**: reads all reports + memory of past decisions → proposes BUY / HOLD / SELL.
4. **Risk team + Portfolio Manager**: aggressive / conservative / neutral debators refine the trade → Portfolio Manager emits the final signal (BUY, OVERWEIGHT, HOLD, UNDERWEIGHT, SELL).

`SignalProcessor.process_signal()` strips the verbose final decision down to one of those five words using a second LLM call.

### Signal-to-action mapping (`config.py`)

```
BUY / OVERWEIGHT   → invest all available cash into SPY at that day's close
SELL / UNDERWEIGHT → liquidate all SPY shares; proceeds go to cash
HOLD               → no trade; cash continues accruing interest
```

All-in / all-out sizing: the system takes a full position on buy signals and exits completely on sell signals.

### Portfolio (`portfolio.py`)

`Portfolio` is the only stateful object. It loads/saves JSON at `state_file`.

- `apply_daily_interest(date, days)` — compound interest on cash using `(1 + SAVINGS_RATE)^(1/365)` per day; `days` is calendar days since the last recorded trading day.
- `execute(signal, price, date)` — applies the trade, appends a record to `trades[]`, saves nothing (caller must call `portfolio.save()`).
- Interest is always applied **before** executing the day's trade.

### Paper trading flow

Both scripts share the same single-day logic. Each checks if a decision already exists for today before calling the agent (idempotent re-runs). Should be scheduled via cron or a task scheduler to fire once per trading day after market close (4:30 PM ET or later).

### Memory / reflection (TradingAgents built-in)

After each decision you can call `ta.reflect_and_remember(returns_loss)` with the dollar P&L of the completed position. This writes lessons to Redis-backed per-agent memories (bull, bear, trader, invest judge, portfolio manager) that are retrieved on future calls. Requires Redis running locally (`redis-server`).

## Configuration Reference (`.env`)

```
LLM_PROVIDER=openai          # openai | anthropic | google | xai | deepseek
OPENAI_API_KEY=sk-...        # or the matching key for your provider
DEEP_THINK_LLM=              # leave blank to use per-provider defaults in config.py
QUICK_THINK_LLM=             # leave blank to use per-provider defaults in config.py
FRED_API_KEY=                    # free key from fred.stlouisfed.org — fetches DFF daily
ALPHA_VANTAGE_API_KEY=           # free key (25 req/day) — enables Alpha Vantage news & sentiment
REDDIT_CLIENT_ID=                # from reddit.com/prefs/apps (script app)
REDDIT_CLIENT_SECRET=            # secret field from the same app
REDDIT_USER_AGENT=spy-trading-agent/1.0
STARTING_BALANCE=100000          # initial portfolio value in USD
# SAVINGS_RATE=0.043             # optional override — if set, skips FRED fetch entirely
```

## Key Files

| File | Role |
|---|---|
| `config.py` | All constants; reads `.env`; calls `rates.py` at startup to set `SAVINGS_RATE` |
| `rates.py` | Fetches DFF from FRED API; 1-day cache in `data/rates_cache.json`; fallback to 4.21% |
| `portfolio.py` | `Portfolio` class — state, interest, trade execution |
| `reddit_tool.py` | PRAW-based LangChain tool; fetches SPY posts from 5 subreddits; graceful fallback if no key |
| `social_analyst_reddit.py` | Replacement social analyst (Reddit + news); apply via `apply_reddit_patch()` before graph init |
| `runner.py` | Shared scheduler: market hours check, 30-min slots, SPY price fetch, cycle logic |
| `paper_trade_full.py` | Version 1 — analysts: `market`, `news`, `fundamentals`; self-contained daily loop |
| `paper_trade_lean.py` | Version 2 — analysts: `market`, `fundamentals` (not yet built) |
| `report.py` | Reads `data/*.json` and prints a performance summary table |
| `data/` | Runtime state — JSON portfolio snapshots; safe to delete to reset |
| `../tradingagents/` | Upstream multi-agent framework; do not edit in this repo |

## Important Constraints

- **Python ≥ 3.10** is required by `tradingagents`. The system Python on this machine is 3.9; always use the venv.
- **LLM cost**: running the full 4-agent pipeline daily is expensive. Reduce `max_debate_rounds` and `max_risk_discuss_rounds` to `1` (already set in `config.py`) to limit token usage.
- **Memory requires no external database**: the BM25 memory system (`rank_bm25`) runs entirely in RAM — no Redis or database needed. Memory is empty on every startup until `reflect_and_remember()` is called to populate it.
- **Market hours**: both scripts should only be run on weekdays after 4:00 PM ET. yfinance returns no data for weekends or holidays.
