from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class Advice:
    action: str
    trend: str
    confidence: int
    entry: float
    stop_loss: float
    take_profit: float
    risk_amount: float
    position_size_oz: float
    notes: str


def _trend(row: pd.Series) -> str:
    close = row["Close"]
    sma20 = row["SMA20"]
    sma50 = row["SMA50"]

    if close > sma50 and sma20 > sma50:
        return "Bullish"
    if close < sma50 and sma20 < sma50:
        return "Bearish"
    return "Sideways"


def _position_size(account_balance: float, risk_pct: float, entry: float, stop: float) -> tuple[float, float]:
    risk_amount = account_balance * (risk_pct / 100)
    risk_per_oz = abs(entry - stop)
    if risk_per_oz <= 0:
        return risk_amount, 0.0
    return risk_amount, risk_amount / risk_per_oz


def build_advice(df: pd.DataFrame, account_balance: float, risk_pct: float) -> Advice:
    if len(df) < 55:
        return Advice(
            action="WAIT",
            trend="Unknown",
            confidence=0,
            entry=0.0,
            stop_loss=0.0,
            take_profit=0.0,
            risk_amount=0.0,
            position_size_oz=0.0,
            notes="Not enough candles yet for reliable indicators.",
        )

    latest = df.iloc[-1]
    previous = df.iloc[-2]

    trend = _trend(latest)
    close = float(latest["Close"])
    rsi = float(latest["RSI14"])
    atr = float(latest["ATR14"])

    action = "WAIT"
    notes = "No clean setup right now."

    if trend == "Bullish" and close > float(latest["SMA20"]) and 45 <= rsi <= 70:
        action = "BUY"
        notes = "Trend and momentum support a long setup."
    elif trend == "Bearish" and close < float(latest["SMA20"]) and 30 <= rsi <= 55:
        action = "SELL"
        notes = "Trend and momentum support a short setup."

    if action == "BUY" or (action == "WAIT" and trend == "Bullish"):
        stop = close - (1.5 * atr)
        target = close + (3.0 * atr)
    elif action == "SELL" or (action == "WAIT" and trend == "Bearish"):
        stop = close + (1.5 * atr)
        target = close - (3.0 * atr)
    else:
        stop = close - (1.0 * atr)
        target = close + (1.0 * atr)

    risk_amount, size_oz = _position_size(account_balance, risk_pct, close, stop)

    confidence = 35
    if trend in {"Bullish", "Bearish"}:
        confidence += 25
    if action != "WAIT":
        confidence += 25
    if (action == "BUY" and close > float(previous["Close"])) or (
        action == "SELL" and close < float(previous["Close"])
    ):
        confidence += 15

    return Advice(
        action=action,
        trend=trend,
        confidence=min(confidence, 95),
        entry=close,
        stop_loss=stop,
        take_profit=target,
        risk_amount=risk_amount,
        position_size_oz=size_oz,
        notes=notes,
    )
