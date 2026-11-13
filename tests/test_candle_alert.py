from datetime import datetime, timezone

import pandas as pd

from src import candle_alert


def _candle_df(high: float, low: float, when: datetime) -> pd.DataFrame:
    index = pd.DatetimeIndex([when])
    return pd.DataFrame(
        {"Open": [low], "High": [high], "Low": [low], "Close": [high], "Volume": [100]},
        index=index,
    )


def test_returns_empty_when_no_data(monkeypatch):
    monkeypatch.setattr(candle_alert, "get_gold_data", lambda **kwargs: pd.DataFrame())
    assert candle_alert.check_large_candle(interval="5m") == ""


def test_returns_empty_when_under_threshold(monkeypatch):
    when = datetime(2026, 11, 13, 6, 0, tzinfo=timezone.utc)
    df = _candle_df(high=4102.0, low=4099.0, when=when)  # 3.0 range
    monkeypatch.setattr(candle_alert, "get_gold_data", lambda **kwargs: df)
    assert candle_alert.check_large_candle(interval="5m", min_length_usd=5.0) == ""


def test_flags_candle_over_threshold(monkeypatch):
    when = datetime(2026, 11, 13, 6, 0, tzinfo=timezone.utc)
    df = _candle_df(high=4108.0, low=4100.0, when=when)  # 8.0 range
    monkeypatch.setattr(candle_alert, "get_gold_data", lambda **kwargs: df)

    result = candle_alert.check_large_candle(interval="5m", min_length_usd=5.0)
    assert "$8.00" in result
    assert "> $5.00" in result
    assert "14:00 PHT" in result  # 06:00 UTC -> 14:00 PHT
