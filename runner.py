"""
Shared scheduler logic for paper_trade_full.py and paper_trade_lean.py.

Handles:
- Market hours check (9:30 AM – 4:00 PM ET, weekdays only)
- 30-minute slot tracking and idempotency
- Current SPY price fetch (intraday)
- One analysis + trade cycle
- Sleep timing between slots
"""

import sys
import os
import time
from datetime import datetime, timezone

import pytz
import yfinance as yf
from rich.console import Console
from rich.rule import Rule

console = Console()
ET = pytz.timezone("America/New_York")

INTERVAL_MINUTES = 30
MARKET_OPEN  = (9, 30)   # hour, minute ET
MARKET_CLOSE = (16, 0)


# ── Time helpers ──────────────────────────────────────────────────────────────

def now_et() -> datetime:
    return datetime.now(ET)


def is_market_hours() -> bool:
    """True if NYSE is currently open (weekday, 9:30 AM – 4:00 PM ET)."""
    now = now_et()
    if now.weekday() >= 5:
        return False
    opens  = now.replace(hour=MARKET_OPEN[0],  minute=MARKET_OPEN[1],  second=0, microsecond=0)
    closes = now.replace(hour=MARKET_CLOSE[0], minute=MARKET_CLOSE[1], second=0, microsecond=0)
    return opens <= now < closes


def current_slot(now: datetime = None) -> str:
    """
    Return the label for the current 30-min slot, e.g. "2026-05-05 09:30".
    Used to prevent running the same slot twice on restart.
    """
    if now is None:
        now = now_et()
    total_min   = now.hour * 60 + now.minute
    slot_start  = (total_min // INTERVAL_MINUTES) * INTERVAL_MINUTES
    sh, sm      = slot_start // 60, slot_start % 60
    return now.strftime(f"%Y-%m-%d {sh:02d}:{sm:02d}")


def seconds_to_next_slot(now: datetime = None) -> int:
    """Seconds until the start of the next 30-min slot."""
    if now is None:
        now = now_et()
    total_sec  = now.hour * 3600 + now.minute * 60 + now.second
    slot_sec   = INTERVAL_MINUTES * 60
    elapsed    = total_sec % slot_sec
    remaining  = slot_sec - elapsed
    return max(remaining, 1)


def is_past_close(now: datetime = None) -> bool:
    if now is None:
        now = now_et()
    closes = now.replace(hour=MARKET_CLOSE[0], minute=MARKET_CLOSE[1], second=0, microsecond=0)
    return now >= closes


# ── Price fetch ───────────────────────────────────────────────────────────────

def get_spy_price() -> float | None:
    """Fetch the latest SPY price (intraday or last close)."""
    try:
        ticker = yf.Ticker("SPY")
        price  = ticker.fast_info.get("last_price") or ticker.fast_info.get("regularMarketPrice")
        if price and price > 0:
            return float(price)
    except Exception:
        pass

    # Fallback: download today's bar
    try:
        df = yf.download("SPY", period="1d", interval="1m", progress=False)
        if not df.empty:
            if hasattr(df.columns, "levels"):
                df.columns = df.columns.droplevel(1)
            return float(df["Close"].iloc[-1])
    except Exception:
        pass

    return None


# ── Single analysis cycle ─────────────────────────────────────────────────────

def run_cycle(ta, portfolio, label: str, logger=None) -> None:
    """Run one analysis + trade cycle and save portfolio state."""
    from config import TICKER

    now         = now_et()
    slot        = current_slot(now)
    trade_dt    = datetime.now(timezone.utc).isoformat()

    console.rule(f"[bold blue]{label} — slot {slot}")

    # Update logger slot so every LLM call this cycle is tagged correctly
    if logger is not None:
        logger.slot = slot

    # ── Idempotency: skip if already ran this slot ─────────────────────────
    if portfolio.last_run_slot == slot:
        console.print(f"  [dim]Already ran slot {slot}, skipping.[/dim]")
        return

    # ── Accrue interest since last run ────────────────────────────────────
    elapsed = portfolio.minutes_since_last_run()
    if elapsed > 0:
        earned = portfolio.apply_interest(elapsed)
        if earned > 0.01:
            console.print(f"  [dim]Interest: +${earned:,.4f} over {elapsed:.1f} min[/dim]")

    # ── Current SPY price ─────────────────────────────────────────────────
    price = get_spy_price()
    if price is None:
        console.print("  [yellow]Could not fetch SPY price — skipping slot.[/yellow]")
        return
    console.print(f"  SPY: [bold]${price:,.2f}[/bold]")

    # ── AI decision ───────────────────────────────────────────────────────
    console.print("  [cyan]Running TradingAgents…[/cyan]")
    try:
        _, signal = ta.propagate(TICKER, now.strftime("%Y-%m-%d"))
    except Exception as exc:
        console.print(f"  [red]Agent error: {exc}[/red]")
        signal = "HOLD"

    console.print(f"  Signal: [bold]{signal}[/bold]")

    # ── Execute trade ─────────────────────────────────────────────────────
    cost_basis_before = portfolio.cost_basis
    shares_before     = portfolio.shares

    trade = portfolio.execute(signal, price, trade_dt, slot)
    portfolio.save()

    console.print(
        f"  Action: [bold]{trade['action']}[/bold]  |  "
        f"Shares: {trade['shares_held']:,.4f}  |  "
        f"Cash: ${trade['cash']:,.2f}  |  "
        f"[green]Total: ${trade['portfolio_value']:,.2f}[/green]"
    )

    # ── Reflect and store lessons when a position closes ──────────────────
    if trade['action'] == 'SELL' and shares_before > 0 and cost_basis_before > 0:
        pnl = (price - cost_basis_before) * shares_before
        console.print(f"  [cyan]Reflecting on closed position (P&L: ${pnl:+,.2f})…[/cyan]")
        try:
            ta.reflect_and_remember(pnl)
            from memory_store import save_memories
            save_memories(ta)
            console.print(f"  [dim]Lessons saved to data/memory/[/dim]")
        except Exception as exc:
            console.print(f"  [yellow]Reflection failed: {exc}[/yellow]")


# ── Scheduler loop ────────────────────────────────────────────────────────────

def run_scheduler(ta, portfolio, label: str, logger=None) -> None:
    """
    Run analysis every 30 minutes during NYSE market hours.
    Blocks until 4:00 PM ET then exits.
    Call this from paper_trade_full.py / paper_trade_lean.py.
    """
    console.rule(f"[bold green]{label} Paper Trading — starting scheduler")
    console.print(f"  Interval : every {INTERVAL_MINUTES} minutes")
    console.print(f"  Hours    : 9:30 AM – 4:00 PM ET (weekdays)")
    console.print(f"  Portfolio: ${portfolio.total_value(get_spy_price() or 0):,.2f}\n")

    while True:
        now = now_et()

        if is_past_close(now):
            console.rule("[bold]Market closed — session complete")
            break

        if not is_market_hours():
            opens = now.replace(
                hour=MARKET_OPEN[0], minute=MARKET_OPEN[1], second=0, microsecond=0
            )
            wait_sec = max((opens - now).total_seconds(), 30)
            console.print(
                f"  [dim]Market not yet open. Waiting {wait_sec/60:.0f} min until 9:30 AM ET…[/dim]"
            )
            time.sleep(min(wait_sec, 300))
            continue

        # Run the analysis for this slot
        run_cycle(ta, portfolio, label, logger=logger)

        # Sleep until the next slot
        secs = seconds_to_next_slot()
        console.print(f"  [dim]Next slot in {secs//60}m {secs%60:02d}s[/dim]\n")
        time.sleep(secs)
