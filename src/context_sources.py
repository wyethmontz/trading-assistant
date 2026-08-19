from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import feedparser
import pandas as pd
import yfinance as yf


# direction_for_gold: +1 means an increase in this asset is generally bullish for gold.
ASSET_DRIVERS = [
    {"symbol": "DX-Y.NYB", "name": "US Dollar Index (DXY)", "weight": 30, "direction_for_gold": -1},
    {"symbol": "^TNX", "name": "US 10Y Yield", "weight": 25, "direction_for_gold": -1},
    {"symbol": "^VIX", "name": "VIX", "weight": 15, "direction_for_gold": 1},
    {"symbol": "CL=F", "name": "WTI Crude", "weight": 10, "direction_for_gold": 1},
    {"symbol": "SI=F", "name": "Silver", "weight": 10, "direction_for_gold": 1},
    {"symbol": "^GSPC", "name": "S&P 500", "weight": 10, "direction_for_gold": -1},
    {"symbol": "TLT", "name": "US 20Y Bond ETF (TLT)", "weight": 5, "direction_for_gold": 1},
    {"symbol": "BTC-USD", "name": "Bitcoin", "weight": 5, "direction_for_gold": -1},
    {"symbol": "GDX", "name": "Gold Miners ETF (GDX)", "weight": 5, "direction_for_gold": 1},
]

EXTERNAL_NEWS_FEEDS = [
    {"source": "Reuters Markets", "url": "https://www.reutersagency.com/feed/?best-topics=markets&post_type=best"},
    {"source": "MarketWatch Commodities", "url": "https://feeds.content.dowjones.io/public/rss/RSSMarketWatchCommodities"},
    {"source": "FXStreet", "url": "https://www.fxstreet.com/rss/news"},
]

BULLISH_GOLD_KEYWORDS = [
    "safe haven",
    "geopolitical",
    "war",
    "tension",
    "inflation",
    "recession",
    "rate cut",
    "dovish",
    "debt",
    "uncertainty",
]

BEARISH_GOLD_KEYWORDS = [
    "rate hike",
    "hawkish",
    "strong dollar",
    "yield rise",
    "risk-on",
    "cooling inflation",
    "ceasefire",
    "equity rally",
]


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df


def get_macro_snapshot(period: str = "5d", interval: str = "1h") -> tuple[pd.DataFrame, float]:
    """Return cross-asset movement and a weighted directional bias score for gold."""
    rows: list[dict[str, Any]] = []
    weighted_score = 0.0

    for driver in ASSET_DRIVERS:
        symbol = driver["symbol"]

        data = yf.download(
            symbol,
            period=period,
            interval=interval,
            auto_adjust=False,
            progress=False,
            threads=False,
        )

        if data.empty:
            continue

        data = _normalize_columns(data)
        close = data["Close"].dropna()
        if len(close) < 2:
            continue

        last = float(close.iloc[-1])
        prev = float(close.iloc[-2])
        if prev == 0:
            continue

        change_pct = ((last - prev) / prev) * 100
        direction_for_gold = int(driver["direction_for_gold"])
        weight = float(driver["weight"])

        # Cap single-factor impact so one volatile proxy does not dominate.
        normalized_move = max(min(change_pct / 0.30, 2.0), -2.0)
        contribution = direction_for_gold * normalized_move * weight
        weighted_score += contribution

        rows.append(
            {
                "Driver": driver["name"],
                "Symbol": symbol,
                "Last": last,
                "Change %": change_pct,
                "Gold Impact": "Bullish" if contribution > 0 else "Bearish" if contribution < 0 else "Neutral",
                "Contribution": contribution,
            }
        )

    if not rows:
        return pd.DataFrame(), 0.0

    snapshot = pd.DataFrame(rows).sort_values("Contribution", ascending=False)

    max_score = sum(driver["weight"] for driver in ASSET_DRIVERS) * 2
    bias_score = 100 * (weighted_score / max_score)
    bias_score = float(max(min(bias_score, 100), -100))

    return snapshot, bias_score


def get_gold_news(limit: int = 8) -> pd.DataFrame:
    """Fetch latest news items attached to the Gold futures ticker from Yahoo Finance."""
    ticker = yf.Ticker("GC=F")
    items = ticker.news or []

    parsed_rows: list[dict[str, str]] = []
    for item in items[:limit]:
        title = str(item.get("title", "")).strip()
        publisher = str(item.get("publisher", "Unknown"))
        link = str(item.get("link", ""))
        ts = item.get("providerPublishTime")

        published = ""
        if isinstance(ts, (int, float)):
            published = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        if not title:
            continue

        parsed_rows.append(
            {
                "Published": published,
                "Publisher": publisher,
                "Headline": title,
                "Link": link,
            }
        )

    return pd.DataFrame(parsed_rows)


def get_external_gold_news(limit_per_feed: int = 4) -> pd.DataFrame:
    """Fetch external macro/commodity headlines and keep gold-relevant titles."""
    rows: list[dict[str, str]] = []
    focus_terms = ["gold", "xau", "fed", "inflation", "yield", "dollar", "treasury", "geopolitical"]

    for feed in EXTERNAL_NEWS_FEEDS:
        parsed = feedparser.parse(feed["url"])
        entries = getattr(parsed, "entries", [])

        kept = 0
        for entry in entries:
            title = str(getattr(entry, "title", "")).strip()
            lower_title = title.lower()
            if not title or not any(term in lower_title for term in focus_terms):
                continue

            link = str(getattr(entry, "link", ""))
            published = str(getattr(entry, "published", ""))
            rows.append(
                {
                    "Published": published,
                    "Publisher": feed["source"],
                    "Headline": title,
                    "Link": link,
                }
            )
            kept += 1
            if kept >= limit_per_feed:
                break

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows)


def score_gold_news_sentiment(news_df: pd.DataFrame) -> float:
    """Return a simple sentiment score in [-100, 100] where positive is bullish for gold."""
    if news_df.empty or "Headline" not in news_df.columns:
        return 0.0

    score = 0
    for headline in news_df["Headline"].dropna().astype(str):
        text = headline.lower()
        for keyword in BULLISH_GOLD_KEYWORDS:
            if keyword in text:
                score += 1
        for keyword in BEARISH_GOLD_KEYWORDS:
            if keyword in text:
                score -= 1

    max_abs = max(len(news_df), 1)
    normalized = (score / max_abs) * 25
    return float(max(min(normalized, 100), -100))
