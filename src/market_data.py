from __future__ import annotations

import pandas as pd
import yfinance as yf


GOLD_SYMBOL = "GC=F"


def get_gold_data(period: str, interval: str) -> pd.DataFrame:
    """Fetch OHLCV data for Gold futures and normalize the columns."""
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
