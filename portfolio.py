"""Portfolio state management with cash, SPY shares, and savings interest."""

import json
import math
from datetime import datetime, timezone
from typing import Optional

from config import STARTING_BALANCE, SAVINGS_RATE, BUY_SIGNALS, SELL_SIGNALS


class Portfolio:
    """Tracks cash, SPY shares, and applies compound savings interest on cash."""

    def __init__(self, state_file: str):
        self.state_file = state_file
        self._load()

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load(self):
        try:
            with open(self.state_file) as f:
                data = json.load(f)
            self.cash: float            = data["cash"]
            self.shares: float          = data["shares"]
            self.cost_basis: float      = data.get("cost_basis", 0.0)
            self.trades: list           = data.get("trades", [])
            self.last_date: Optional[str]     = data.get("last_date")
            self.last_run_dt: Optional[str]   = data.get("last_run_dt")
            self.last_run_slot: Optional[str] = data.get("last_run_slot")
            self.interest_earned: float = data.get("interest_earned", 0.0)
        except (FileNotFoundError, json.JSONDecodeError):
            self.cash           = STARTING_BALANCE
            self.shares         = 0.0
            self.cost_basis     = 0.0
            self.trades         = []
            self.last_date      = None
            self.last_run_dt    = None
            self.last_run_slot  = None
            self.interest_earned = 0.0

    def save(self):
        with open(self.state_file, "w") as f:
            json.dump(
                {
                    "cash":             self.cash,
                    "shares":           self.shares,
                    "cost_basis":       self.cost_basis,
                    "trades":           self.trades,
                    "last_date":        self.last_date,
                    "last_run_dt":      self.last_run_dt,
                    "last_run_slot":    self.last_run_slot,
                    "interest_earned":  self.interest_earned,
                },
                f,
                indent=2,
            )

    # ── Interest ──────────────────────────────────────────────────────────────

    def apply_interest(self, elapsed_minutes: float) -> float:
        """
        Accrue savings-rate interest on cash for elapsed_minutes of real time.
        Uses continuous compound approximation: (1 + daily_rate)^(minutes/1440).
        """
        if self.cash <= 0 or elapsed_minutes <= 0:
            return 0.0
        elapsed_days = elapsed_minutes / 1440.0
        daily_rate   = (1 + SAVINGS_RATE) ** (1 / 365) - 1
        earned       = self.cash * ((1 + daily_rate) ** elapsed_days - 1)
        self.cash           += earned
        self.interest_earned += earned
        return earned

    def minutes_since_last_run(self) -> float:
        """Return minutes elapsed since last recorded run (0 if never run)."""
        if not self.last_run_dt:
            return 0.0
        last = datetime.fromisoformat(self.last_run_dt)
        now  = datetime.now(timezone.utc)
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        return max((now - last).total_seconds() / 60.0, 0.0)

    # ── Trade execution ───────────────────────────────────────────────────────

    def execute(self, signal: str, price: float, trade_dt: str, slot: str) -> dict:
        """
        Apply a trading signal and return a trade record.
        signal:   BUY | OVERWEIGHT | HOLD | UNDERWEIGHT | SELL
        price:    current SPY price
        trade_dt: ISO datetime string of this run
        slot:     30-min slot label e.g. "2026-05-05 09:30"
        """
        action = signal.upper()

        if action in BUY_SIGNALS and self.cash > 0:
            shares_bought = math.floor(self.cash / price * 10000) / 10000
            spent = shares_bought * price
            self.cost_basis = price if self.shares == 0 else (
                (self.cost_basis * self.shares + spent) / (self.shares + shares_bought)
            )
            self.shares += shares_bought
            self.cash   -= spent
            record_action = "BUY"
            shares_delta  = shares_bought

        elif action in SELL_SIGNALS and self.shares > 0:
            proceeds     = self.shares * price
            shares_sold  = self.shares
            self.cash   += proceeds
            self.shares  = 0.0
            self.cost_basis = 0.0
            record_action = "SELL"
            shares_delta  = -shares_sold

        else:
            record_action = "HOLD"
            shares_delta  = 0.0

        total_value = self.cash + self.shares * price
        trade_date  = trade_dt[:10]  # YYYY-MM-DD portion

        trade = {
            "datetime":             trade_dt,
            "slot":                 slot,
            "date":                 trade_date,
            "signal":               signal,
            "action":               record_action,
            "price":                round(price, 4),
            "shares_delta":         round(shares_delta, 6),
            "shares_held":          round(self.shares, 6),
            "cash":                 round(self.cash, 2),
            "portfolio_value":      round(total_value, 2),
            "interest_earned_total": round(self.interest_earned, 2),
        }

        self.trades.append(trade)
        self.last_date     = trade_date
        self.last_run_dt   = trade_dt
        self.last_run_slot = slot
        return trade

    # ── Helpers ───────────────────────────────────────────────────────────────

    def total_value(self, spy_price: float) -> float:
        return round(self.cash + self.shares * spy_price, 2)

    def return_pct(self, spy_price: float) -> float:
        return round((self.total_value(spy_price) / STARTING_BALANCE - 1) * 100, 2)

    def summary(self, spy_price: float) -> dict:
        return {
            "cash":              round(self.cash, 2),
            "shares":            round(self.shares, 6),
            "spy_price":         spy_price,
            "equity_value":      round(self.shares * spy_price, 2),
            "total_value":       self.total_value(spy_price),
            "starting_balance":  STARTING_BALANCE,
            "total_return_pct":  self.return_pct(spy_price),
            "interest_earned":   round(self.interest_earned, 2),
            "trades_count":      len(self.trades),
        }
