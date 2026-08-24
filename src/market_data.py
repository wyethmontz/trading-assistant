from __future__ import annotations

import pandas as pd
import yfinance as yf


GOLD_SYMBOL = "PAXG-USD"  # PAX Gold: token backed 1:1 by physical gold, trades 24/7.
# Tracks spot/CFD gold (e.g. XM's XAUUSD) far more closely than GC=F futures,
# which can drift ~$50-60 away from spot due to contract roll and session gaps.


def get_gold_data(period: str, interval: str) -> pd.DataFrame:
    """Fetch OHLCV data for gold (via PAXG-USD spot proxy) and normalize the columns."""
    df = yf.download(
        GOLD_SYMBOL,
        period=period,
        interval=interval,
        auto_adjust=False,
        progress=False,
        threads=False,
    )

    if df.empty:
        return df

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    columns = ["Open", "High", "Low", "Close", "Volume"]
    df = df[columns].dropna()
    return df


def get_latest_price(interval: str = "1m") -> tuple[float, pd.Timestamp] | tuple[None, None]:
    """Fetch the most recent close price for a low-latency price check (default 1m candles)."""
    df = get_gold_data(period="1d", interval=interval)
    if df.empty:
        return None, None
    return float(df["Close"].iloc[-1]), df.index[-1]
