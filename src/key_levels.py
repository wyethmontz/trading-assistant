from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd


@dataclass
class KeyLevels:
    """Informational reference price levels. Never fed into entry/SL/TP or any guardrail."""

    swing_high: float | None = None
    swing_low: float | None = None
    prior_day_high: float | None = None
    prior_day_low: float | None = None
    prior_week_high: float | None = None
    prior_week_low: float | None = None
    round_number_above: float | None = None
    round_number_below: float | None = None


def _find_last_swing(values: pd.Series, n: int, mode: str) -> float | None:
    """Most recent confirmed pivot: the extreme of a 2n+1 bar window centered on it.

    Scans from the most recent confirmable bar backward and returns the first match.
    The trailing `n` bars are excluded automatically, since they don't yet have `n`
    bars after them to confirm a pivot.
    """
    arr = values.to_numpy()
    length = len(arr)
    if length < 2 * n + 1:
        return None

    for i in range(length - 1 - n, n - 1, -1):
        window = arr[i - n : i + n + 1]
        center = arr[i]
        if mode == "high" and center == window.max():
            return float(center)
        if mode == "low" and center == window.min():
            return float(center)
    return None


def _prior_period_high_low(df: pd.DataFrame, freq: str) -> tuple[float, float] | None:
    """High/low of the most recently *completed* period (day or week), excluding the
    still-in-progress current one. `freq` is a pandas period alias ('D' or 'W')."""
    if df.empty:
        return None

    index = df.index
    if index.tz is not None:
        index = index.tz_convert("UTC").tz_localize(None)
    periods = index.to_period(freq)
    unique_periods = sorted(periods.unique())
    if len(unique_periods) < 2:
        return None

    prior_period = unique_periods[-2]
    prior_rows = df.loc[periods == prior_period]
    return float(prior_rows["High"].max()), float(prior_rows["Low"].min())


def _round_step(price: float) -> float:
    """Psychological round-number spacing, scaled to price magnitude."""
    if price >= 10_000:
        return 500.0
    if price >= 1_000:
        return 100.0
    if price >= 100:
        return 10.0
    if price >= 10:
        return 1.0
    if price >= 1:
        return 0.10
    return 0.01


def _round_numbers_straddling(price: float) -> tuple[float, float]:
    """Nearest round levels strictly below and above `price` (returns (below, above))."""
    step = _round_step(price)

    below = math.floor(price / step) * step
    if math.isclose(below, price, rel_tol=1e-9, abs_tol=1e-9):
        below -= step

    above = math.ceil(price / step) * step
    if math.isclose(above, price, rel_tol=1e-9, abs_tol=1e-9):
        above += step

    return round(below, 2), round(above, 2)


def compute_key_levels(df: pd.DataFrame, current_price: float, swing_lookback: int = 5) -> KeyLevels:
    """Compute all key levels from OHLC history. Gracefully omits (None) any level
    that can't be computed from the available candle history."""
    swing_high = _find_last_swing(df["High"], swing_lookback, "high") if not df.empty else None
    swing_low = _find_last_swing(df["Low"], swing_lookback, "low") if not df.empty else None

    prior_day = _prior_period_high_low(df, "D")
    prior_week = _prior_period_high_low(df, "W")

    round_below, round_above = _round_numbers_straddling(current_price)

    return KeyLevels(
        swing_high=swing_high,
        swing_low=swing_low,
        prior_day_high=prior_day[0] if prior_day else None,
        prior_day_low=prior_day[1] if prior_day else None,
        prior_week_high=prior_week[0] if prior_week else None,
        prior_week_low=prior_week[1] if prior_week else None,
        round_number_above=round_above,
        round_number_below=round_below,
    )
