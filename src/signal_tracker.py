from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from src.market_data import get_gold_data


SIGNAL_LOG_PATH = Path("data/signal_log.csv")

COLUMNS = [
    "timestamp",
    "action",
    "entry",
    "stop",
    "target",
    "confidence",
    "trend",
    "actionable",
    "status",
    "resolved_at",
    "resolved_price",
]


def _ensure_log_file() -> None:
    SIGNAL_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not SIGNAL_LOG_PATH.exists():
        pd.DataFrame(columns=COLUMNS).to_csv(SIGNAL_LOG_PATH, index=False)


def load_signal_log() -> pd.DataFrame:
    _ensure_log_file()
    df = pd.read_csv(SIGNAL_LOG_PATH)
    if not df.empty:
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
        df["resolved_at"] = pd.to_datetime(df["resolved_at"], utc=True, errors="coerce")
    return df


def log_signal(
    now: datetime,
    action: str,
    entry: float,
    stop: float,
    target: float,
    confidence: int,
    trend: str,
    actionable: bool,
) -> None:
    """Log a rule-fired BUY/SELL for outcome tracking, regardless of whether it was
    actually tradable right now. `actionable` records whether it survived the
    guardrails (feasibility/confidence/adaptive), so we can learn if the rule
    itself is right even during stretches where nothing is tradable yet."""
    _ensure_log_file()
    df = pd.read_csv(SIGNAL_LOG_PATH)

    if not df.empty:
        last = df.iloc[-1]
        same_open_signal = (
            last["status"] == "open"
            and last["action"] == action
            and math.isclose(last["entry"], entry, rel_tol=1e-9)
            and math.isclose(last["stop"], stop, rel_tol=1e-9)
            and math.isclose(last["target"], target, rel_tol=1e-9)
        )
        if same_open_signal:
            return

    row = {
        "timestamp": now.isoformat(),
        "action": action,
        "entry": entry,
        "stop": stop,
        "target": target,
        "confidence": confidence,
        "trend": trend,
        "actionable": actionable,
        "status": "open",
        "resolved_at": "",
        "resolved_price": "",
    }
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    df.to_csv(SIGNAL_LOG_PATH, index=False)


def resolve_open_signals() -> None:
    """Check open signals against price history since they were logged; mark win/loss if stop or target was hit."""
    df = load_signal_log()
    if df.empty:
        return

    open_mask = df["status"] == "open"
    if not open_mask.any():
        return

    price_df = get_gold_data(period="3mo", interval="1h")
    if price_df.empty:
        return

    changed = False
    for idx in df[open_mask].index:
        row = df.loc[idx]
        after = price_df[price_df.index > row["timestamp"]]
        if after.empty:
            continue

        if row["action"] == "BUY":
            hit_stop = after["Low"] <= row["stop"]
            hit_target = after["High"] >= row["target"]
        else:
            hit_stop = after["High"] >= row["stop"]
            hit_target = after["Low"] <= row["target"]

        stop_time = after.index[hit_stop][0] if hit_stop.any() else None
        target_time = after.index[hit_target][0] if hit_target.any() else None

        if stop_time is None and target_time is None:
            continue

        if stop_time is not None and (target_time is None or stop_time <= target_time):
            df.loc[idx, "status"] = "loss"
            df.loc[idx, "resolved_price"] = row["stop"]
            df.loc[idx, "resolved_at"] = stop_time.isoformat()
        else:
            df.loc[idx, "status"] = "win"
            df.loc[idx, "resolved_price"] = row["target"]
            df.loc[idx, "resolved_at"] = target_time.isoformat()
        changed = True

    if changed:
        df.to_csv(SIGNAL_LOG_PATH, index=False)


@dataclass
class SignalStats:
    total: int
    resolved: int
    wins: int
    losses: int
    open_count: int
    win_rate: float
    actionable_resolved: int
    actionable_wins: int
    actionable_win_rate: float


def get_signal_stats() -> SignalStats:
    df = load_signal_log()
    if df.empty:
        return SignalStats(
            total=0, resolved=0, wins=0, losses=0, open_count=0, win_rate=0.0,
            actionable_resolved=0, actionable_wins=0, actionable_win_rate=0.0,
        )

    resolved_mask = df["status"].isin(["win", "loss"])
    wins = int((df["status"] == "win").sum())
    losses = int((df["status"] == "loss").sum())
    open_count = int((df["status"] == "open").sum())
    resolved = wins + losses
    win_rate = (wins / resolved * 100) if resolved else 0.0

    actionable_resolved_df = df[resolved_mask & (df["actionable"] == True)]  # noqa: E712
    actionable_resolved = len(actionable_resolved_df)
    actionable_wins = int((actionable_resolved_df["status"] == "win").sum())
    actionable_win_rate = (actionable_wins / actionable_resolved * 100) if actionable_resolved else 0.0

    return SignalStats(
        total=len(df),
        resolved=resolved,
        wins=wins,
        losses=losses,
        open_count=open_count,
        win_rate=win_rate,
        actionable_resolved=actionable_resolved,
        actionable_wins=actionable_wins,
        actionable_win_rate=actionable_win_rate,
    )
