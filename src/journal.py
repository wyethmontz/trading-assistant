from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


JOURNAL_PATH = Path("data/trade_journal.csv")


@dataclass
class JournalStats:
    total_closed: int
    win_rate: float
    loss_rate: float
    avg_pnl: float
    loss_streak: int
    recommended_risk_cap: float
    recommended_confidence_floor: int
    suggestions: list[str]


def _ensure_journal_file() -> None:
    JOURNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    if JOURNAL_PATH.exists():
        return

    columns = [
        "timestamp",
        "symbol",
        "mode",
        "signal",
        "entry",
        "stop_loss",
        "take_profit",
        "suggested_lots",
        "risk_pct",
        "macro_bias",
        "news_sentiment",
        "confidence",
        "outcome",
        "pnl_usd",
        "notes",
    ]
    pd.DataFrame(columns=columns).to_csv(JOURNAL_PATH, index=False)


def load_journal() -> pd.DataFrame:
    _ensure_journal_file()
    df = pd.read_csv(JOURNAL_PATH)
    if df.empty:
        return df

    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    return df


def append_trade(row: dict[str, object]) -> None:
    _ensure_journal_file()

    payload = {
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "symbol": row.get("symbol", "XAUUSD"),
        "mode": row.get("mode", ""),
        "signal": row.get("signal", "WAIT"),
        "entry": float(row.get("entry", 0.0)),
        "stop_loss": float(row.get("stop_loss", 0.0)),
        "take_profit": float(row.get("take_profit", 0.0)),
        "suggested_lots": float(row.get("suggested_lots", 0.0)),
        "risk_pct": float(row.get("risk_pct", 0.0)),
        "macro_bias": float(row.get("macro_bias", 0.0)),
        "news_sentiment": float(row.get("news_sentiment", 0.0)),
        "confidence": int(row.get("confidence", 0)),
        "outcome": str(row.get("outcome", "Open")),
        "pnl_usd": float(row.get("pnl_usd", 0.0)),
        "notes": str(row.get("notes", "")),
    }

    pd.DataFrame([payload]).to_csv(JOURNAL_PATH, mode="a", header=False, index=False)


def _current_loss_streak(df: pd.DataFrame) -> int:
    streak = 0
    ordered = df.sort_values("timestamp", ascending=False)
    for _, row in ordered.iterrows():
        outcome = str(row.get("outcome", ""))
        if outcome != "Loss":
            break
        streak += 1
    return streak


def get_journal_stats(df: pd.DataFrame, lookback: int = 30) -> JournalStats:
    if df.empty:
        return JournalStats(
            total_closed=0,
            win_rate=0.0,
            loss_rate=0.0,
            avg_pnl=0.0,
            loss_streak=0,
            recommended_risk_cap=1.0,
            recommended_confidence_floor=60,
            suggestions=["No closed trades logged yet. Start journaling each trade result."],
        )

    scoped = df.tail(lookback).copy()
    scoped = scoped[scoped["outcome"].isin(["Win", "Loss", "Breakeven"])].copy()

    if scoped.empty:
        return JournalStats(
            total_closed=0,
            win_rate=0.0,
            loss_rate=0.0,
            avg_pnl=0.0,
            loss_streak=0,
            recommended_risk_cap=1.0,
            recommended_confidence_floor=60,
            suggestions=["Only open trades found. Log Win/Loss/Breakeven once closed."],
        )

    wins = int((scoped["outcome"] == "Win").sum())
    losses = int((scoped["outcome"] == "Loss").sum())
    total = len(scoped)

    win_rate = (wins / total) * 100
    loss_rate = (losses / total) * 100
    avg_pnl = float(scoped["pnl_usd"].mean()) if "pnl_usd" in scoped.columns else 0.0
    streak = _current_loss_streak(scoped)

    recommended_risk = 1.0
    recommended_conf = 60
    suggestions: list[str] = []

    if loss_rate >= 60:
        recommended_risk = 0.35
        recommended_conf = 75
        suggestions.append("High loss rate: cut risk to 0.35% and only take high-confidence setups.")
    elif loss_rate >= 45:
        recommended_risk = 0.50
        recommended_conf = 70
        suggestions.append("Loss rate elevated: reduce risk to 0.50% and require stronger signal confirmation.")

    if streak >= 2:
        recommended_risk = min(recommended_risk, 0.30)
        recommended_conf = max(recommended_conf, 78)
        suggestions.append("Two or more losses in a row: pause lower-quality trades and tighten confidence filter.")

    loss_rows = scoped[scoped["outcome"] == "Loss"].copy()
    if not loss_rows.empty and {"signal", "macro_bias"}.issubset(loss_rows.columns):
        against_macro = 0
        for _, row in loss_rows.iterrows():
            signal = str(row["signal"])
            macro_bias = float(row["macro_bias"])
            if (signal == "BUY" and macro_bias < 0) or (signal == "SELL" and macro_bias > 0):
                against_macro += 1
        if against_macro / len(loss_rows) >= 0.5:
            suggestions.append("Most losses were against macro bias; avoid counter-bias entries.")

    if not suggestions:
        suggestions.append("Performance is stable. Keep risk discipline and continue journaling.")

    return JournalStats(
        total_closed=total,
        win_rate=win_rate,
        loss_rate=loss_rate,
        avg_pnl=avg_pnl,
        loss_streak=streak,
        recommended_risk_cap=recommended_risk,
        recommended_confidence_floor=recommended_conf,
        suggestions=suggestions,
    )
