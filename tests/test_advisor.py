import pandas as pd

from src.advisor import build_advice


def _make_df(close_values, rsi_values=None):
    close_values = list(close_values)
    n = len(close_values)
    sma20 = []
    sma50 = []

    for i in range(n):
        sma20.append(sum(close_values[max(0, i - 19): i + 1]) / min(20, i + 1))
        sma50.append(sum(close_values[max(0, i - 49): i + 1]) / min(50, i + 1))

    if rsi_values is None:
        rsi_values = [60.0] * n

    return pd.DataFrame(
        {
            "Close": close_values,
            "SMA20": sma20,
            "SMA50": sma50,
            "RSI14": rsi_values,
            "ATR14": [10.0] * n,
        }
    )


def test_build_advice_returns_buy_for_bullish_setup():
    closes = [4400 + i for i in range(55)]
    advice = build_advice(_make_df(closes), account_balance=1000.0, risk_pct=1.0)

    assert advice.action == "BUY"
    assert advice.trend == "Bullish"
    assert advice.confidence > 0
    assert advice.entry > 0
    assert advice.stop_loss < advice.entry
    assert advice.take_profit > advice.entry


def test_build_advice_returns_sell_for_bearish_setup():
    closes = [4455 - i for i in range(55)]
    rsi_values = [45.0] * len(closes)
    advice = build_advice(_make_df(closes, rsi_values=rsi_values), account_balance=1000.0, risk_pct=1.0)

    assert advice.action == "SELL"
    assert advice.trend == "Bearish"
    assert advice.confidence > 0
    assert advice.entry > 0
    assert advice.stop_loss > advice.entry
    assert advice.take_profit < advice.entry


def test_build_advice_waits_when_not_enough_data():
    short_df = _make_df([4400 + i for i in range(30)])
    advice = build_advice(short_df, account_balance=1000.0, risk_pct=1.0)

    assert advice.action == "WAIT"
    assert advice.confidence == 0
