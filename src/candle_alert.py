from __future__ import annotations

from datetime import timezone

from src.economic_calendar import _format_ph_time
from src.market_data import get_gold_data


def check_large_candle(interval: str, min_length_usd: float = 5.0, period: str = "5d") -> str:
    """Return a note if the latest `interval` candle's High-Low range exceeds `min_length_usd`.

    Returns "" if the range doesn't exceed the threshold, or the data can't be fetched.
    """
    df = get_gold_data(period=period, interval=interval)
    if df.empty:
        return ""

    latest = df.iloc[-1]
    length = float(latest["High"] - latest["Low"])
    if length <= min_length_usd:
        return ""

    timestamp = df.index[-1].to_pydatetime()
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)

    return f"Range ${length:.2f} (> ${min_length_usd:.2f}) at {_format_ph_time(timestamp)}"
