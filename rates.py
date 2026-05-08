"""
Fetch the current savings benchmark rate from FRED.

Series used: DFF — Effective Federal Funds Rate (daily)
API docs: https://fred.stlouisfed.org/docs/api/fred/

Requires FRED_API_KEY in .env (free at https://fred.stlouisfed.org/docs/api/api_key.html)
"""

import json
import os
from datetime import date, datetime, timedelta

import requests

FRED_API_KEY = os.getenv("FRED_API_KEY", "")
SERIES_ID = "DFF"
FRED_URL = "https://api.stlouisfed.org/fred/series/observations"

_CACHE_FILE = os.path.join(os.path.dirname(__file__), "data", "rates_cache.json")
_FALLBACK_RATE = 0.0421  # 4.21% — Bankrate best HYSA, April 2026
_CACHE_TTL_DAYS = 1


def _load_cache() -> dict:
    try:
        with open(_CACHE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_cache(rate: float):
    os.makedirs(os.path.dirname(_CACHE_FILE), exist_ok=True)
    with open(_CACHE_FILE, "w") as f:
        json.dump({"rate": rate, "fetched_on": date.today().isoformat()}, f)


def _cache_is_fresh(cache: dict) -> bool:
    fetched = cache.get("fetched_on")
    if not fetched:
        return False
    age = (date.today() - datetime.strptime(fetched, "%Y-%m-%d").date()).days
    return age < _CACHE_TTL_DAYS


def get_savings_rate(verbose: bool = False) -> float:
    """
    Return the current IORB rate as a decimal (e.g. 0.0433 for 4.33%).
    Falls back to the hardcoded default if FRED_API_KEY is missing or the
    request fails. Result is cached for 1 day.
    """
    cache = _load_cache()
    if _cache_is_fresh(cache):
        rate = cache["rate"]
        if verbose:
            print(f"[rates] Using cached IORB rate: {rate*100:.2f}% (fetched {cache['fetched_on']})")
        return rate

    if not FRED_API_KEY:
        if verbose:
            print(f"[rates] FRED_API_KEY not set — using fallback rate: {_FALLBACK_RATE*100:.2f}%")
        return _FALLBACK_RATE

    try:
        resp = requests.get(
            FRED_URL,
            params={
                "series_id": SERIES_ID,
                "api_key": FRED_API_KEY,
                "file_type": "json",
                "sort_order": "desc",
                "limit": 1,
            },
            timeout=10,
        )
        resp.raise_for_status()
        observations = resp.json().get("observations", [])
        if not observations:
            raise ValueError("Empty observations list from FRED")

        raw = observations[0]["value"]
        if raw == ".":
            raise ValueError("FRED returned missing value marker '.'")

        # FRED returns IORB as a percentage (e.g. "4.33"), convert to decimal
        rate = float(raw) / 100
        _save_cache(rate)
        if verbose:
            print(f"[rates] Fetched DFF from FRED: {rate*100:.2f}% (as of {observations[0]['date']})")
        return rate

    except Exception as exc:
        if verbose:
            print(f"[rates] FRED fetch failed ({exc}) — using fallback rate: {_FALLBACK_RATE*100:.2f}%")
        return _FALLBACK_RATE
