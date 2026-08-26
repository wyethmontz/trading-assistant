from __future__ import annotations

import pandas as pd
import yfinance as yf


GOLD_SYMBOL = "XAUUSD=X"  # Yahoo's gold spot (XAU/USD) ticker, matches broker quotes
# (e.g. XM's XAUUSD) far more closely than PAXG-USD, whose price can drift from
# spot since it trades as a crypto token with its own supply/demand, or GC=F
# futures, which can drift ~$50-60 away from spot due to contract roll and gaps.


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
