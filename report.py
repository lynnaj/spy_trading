"""
Performance report viewer.

Usage:
    python report.py                  # shows full portfolio report
    python report.py --trades         # show full trade history
"""

import argparse
import json
import os
import sys
from datetime import datetime

from rich.console import Console
from rich.table import Table
from rich import box

from config import STARTING_BALANCE, PAPER_FULL_STATE_FILE
from runner import get_spy_price

console = Console()


def load_portfolio(path: str) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        console.print(f"[red]No portfolio file found at {path}[/red]")
        console.print("Run paper_trade_full.py first to generate data.")
        sys.exit(1)


def action_color(action: str) -> str:
    return {"BUY": "green", "SELL": "red", "HOLD": "dim"}.get(action, "white")


def print_report(data: dict, current_price: float, show_trades: bool):
    cash       = data["cash"]
    shares     = data["shares"]
    equity     = shares * current_price
    total      = cash + equity
    ret_pct    = (total / STARTING_BALANCE - 1) * 100
    interest   = data.get("interest_earned", 0)
    trades     = data.get("trades", [])
    last_slot  = data.get("last_run_slot", "—")

    # ── Summary ──────────────────────────────────────────────────────────────
    console.rule("[bold blue]SPY Paper Trading — FULL Report")

    summary = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    summary.add_column("Field", style="bold")
    summary.add_column("Value")

    ret_color = "green" if ret_pct >= 0 else "red"
    summary.add_row("Starting balance",  f"${STARTING_BALANCE:>12,.2f}")
    summary.add_row("Current SPY price", f"${current_price:>12,.2f}")
    summary.add_row("Cash",              f"${cash:>12,.2f}")
    summary.add_row("Shares held",       f"{shares:>15,.4f}")
    summary.add_row("Equity value",      f"${equity:>12,.2f}")
    summary.add_row("Portfolio total",   f"[bold]${total:>12,.2f}[/bold]")
    summary.add_row("Total return",      f"[{ret_color}]{ret_pct:>+14.2f}%[/{ret_color}]")
    summary.add_row("Interest earned",   f"${interest:>12,.2f}")
    summary.add_row("Total trades",      f"{len(trades):>15}")
    summary.add_row("Last slot run",     f"{last_slot:>15}")
    console.print(summary)

    # ── Action breakdown ─────────────────────────────────────────────────────
    buys  = sum(1 for t in trades if t["action"] == "BUY")
    sells = sum(1 for t in trades if t["action"] == "SELL")
    holds = sum(1 for t in trades if t["action"] == "HOLD")
    console.print(f"  Actions — [green]BUY: {buys}[/green]  [red]SELL: {sells}[/red]  [dim]HOLD: {holds}[/dim]\n")

    # ── Trade history ─────────────────────────────────────────────────────────
    if not show_trades:
        console.print("[dim]Run with --trades to see full trade history.[/dim]")
        return

    console.rule("[bold]Trade History")
    table = Table(box=box.SIMPLE_HEAD)
    table.add_column("Slot",          style="dim",   no_wrap=True)
    table.add_column("Signal",        justify="center")
    table.add_column("Action",        justify="center")
    table.add_column("SPY Price",     justify="right")
    table.add_column("Shares Δ",      justify="right")
    table.add_column("Shares Held",   justify="right")
    table.add_column("Cash",          justify="right")
    table.add_column("Portfolio",     justify="right")

    for t in trades:
        color = action_color(t["action"])
        table.add_row(
            t.get("slot", t.get("date", "—")),
            f"[{color}]{t['signal']}[/{color}]",
            f"[{color}]{t['action']}[/{color}]",
            f"${t['price']:,.2f}",
            f"{t['shares_delta']:+.4f}",
            f"{t['shares_held']:,.4f}",
            f"${t['cash']:,.2f}",
            f"${t['portfolio_value']:,.2f}",
        )
    console.print(table)


def main():
    parser = argparse.ArgumentParser(description="SPY Paper Trading Report")
    parser.add_argument("--trades", action="store_true", help="Show full trade history")
    args = parser.parse_args()

    data  = load_portfolio(PAPER_FULL_STATE_FILE)
    price = get_spy_price() or (
        data["trades"][-1]["price"] if data.get("trades") else 0
    )
    print_report(data, price, args.trades)


if __name__ == "__main__":
    main()
