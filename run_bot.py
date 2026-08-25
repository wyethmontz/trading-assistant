from __future__ import annotations

import os
from datetime import datetime, timezone

from src.advisor import build_advice
from src.broker_guardrails import BrokerSpec, evaluate_trade_feasibility
from src.context_sources import get_external_gold_news, get_gold_news, get_macro_snapshot, score_gold_news_sentiment
from src.indicators import add_indicators
from src.journal import get_journal_stats, load_journal
from src.market_data import get_gold_data
from src.notifier import send_telegram
from src.signal_tracker import log_signal, resolve_open_signals


def _env_float(name: str, default: float) -> float:
    value = os.environ.get(name, "")
    return float(value) if value else default


def build_message(
    now: datetime,
    execution_signal: str,
    downgraded: bool,
    advice,
    feasibility,
    effective_risk_pct: float,
) -> str:
    signal_line = f"<b>Signal: {execution_signal}</b>"
    if downgraded:
        signal_line += " (downgraded from advisor by guardrails)"

    price_label = f"{execution_signal.capitalize()} When Price is" if execution_signal in ("BUY", "SELL") else "Entry"
    stop_distance = abs(advice.entry - advice.stop_loss)
    target_distance = abs(advice.take_profit - advice.entry)

    return (
        f"<b>Gold Signal — {now.strftime('%Y-%m-%d %H:%M UTC')}</b>\n\n"
        f"{signal_line}\n"
        f"Trend: {advice.trend} | Confidence: {advice.confidence}%\n\n"
        f"Lot(s): {feasibility.rounded_lots:.3f}\n"
        f"{price_label}: ${advice.entry:,.2f}\n"
        f"Take Profit Level: ${advice.take_profit:,.2f}\n"
        f"Stop Loss Level: ${advice.stop_loss:,.2f}\n"
        f"Entry - SL: ${stop_distance:,.2f}\n"
        f"TP - Entry: ${target_distance:,.2f}\n\n"
        f"Risk: ${advice.risk_amount:,.2f} ({effective_risk_pct:.2f}%)\n"
        f"Suggested Size: {advice.position_size_oz:,.2f} oz"
    )


def main() -> None:
    now = datetime.now(timezone.utc)

    account_balance = _env_float("ACCOUNT_BALANCE", 64.18)
    risk_pct = _env_float("RISK_PCT", 0.5)
    confidence_floor = _env_float("CONFIDENCE_FLOOR", 65)
    adaptive_mode = os.environ.get("ADAPTIVE_MODE", "true").lower() != "false"

    xm_symbol = os.environ.get("XM_SYMBOL", "XAUUSD")
    contract_size = _env_float("CONTRACT_SIZE", 100.0)
    min_lot = _env_float("MIN_LOT", 0.01)
    lot_step = _env_float("LOT_STEP", 0.01)
    max_lot = _env_float("MAX_LOT", 50.0)
    spread_usd = _env_float("SPREAD_USD", 0.5)

    print("Fetching gold data (Swing 1h)...")
    raw_df = get_gold_data(period="1mo", interval="1h")
    if raw_df.empty:
        print("No market data returned, aborting run.")
        return

    analysis_df = add_indicators(raw_df).dropna().copy()
    if analysis_df.empty:
        print("Indicators not ready yet (insufficient lookback), aborting run.")
        return

    advice = build_advice(analysis_df, account_balance=account_balance, risk_pct=risk_pct)

    print("Fetching macro snapshot and news...")
    macro_df, macro_bias = get_macro_snapshot(period="1mo", interval="1d")
    yahoo_news = get_gold_news(limit=8)
    external_news = get_external_gold_news(limit_per_feed=4)
    news_df = yahoo_news
    if not external_news.empty:
        import pandas as pd

        news_df = pd.concat([yahoo_news, external_news], ignore_index=True).drop_duplicates(subset=["Headline"])
    news_sentiment = score_gold_news_sentiment(news_df)

    journal_df = load_journal()
    journal_stats = get_journal_stats(journal_df)

    effective_risk_pct = risk_pct
    effective_confidence_floor = confidence_floor
    if adaptive_mode:
        effective_risk_pct = min(risk_pct, journal_stats.recommended_risk_cap)
        effective_confidence_floor = max(confidence_floor, journal_stats.recommended_confidence_floor)

    spec = BrokerSpec(
        symbol=xm_symbol,
        contract_size_oz_per_lot=contract_size,
        min_lot=min_lot,
        lot_step=lot_step,
        max_lot=max_lot,
        spread_usd=spread_usd,
    )
    feasibility = evaluate_trade_feasibility(
        account_balance=account_balance,
        risk_pct=effective_risk_pct,
        entry=advice.entry,
        stop=advice.stop_loss,
        spec=spec,
    )

    source_alignment = True
    if advice.action == "BUY":
        source_alignment = macro_bias >= 0 and news_sentiment >= -10
    elif advice.action == "SELL":
        source_alignment = macro_bias <= 0 and news_sentiment <= 10

    execution_signal = advice.action
    if advice.action != "WAIT":
        if advice.confidence < effective_confidence_floor:
            execution_signal = "WAIT"
        if not feasibility.tradable:
            execution_signal = "WAIT"
        if adaptive_mode and journal_stats.loss_streak >= 2 and not source_alignment:
            execution_signal = "WAIT"

    downgraded = execution_signal != advice.action

    print("Resolving open tracked signals against fresh price data...")
    resolve_open_signals()

    if advice.action in ("BUY", "SELL"):
        log_signal(
            now=now,
            action=advice.action,
            entry=advice.entry,
            stop=advice.stop_loss,
            target=advice.take_profit,
            confidence=advice.confidence,
            trend=advice.trend,
            actionable=(execution_signal == advice.action),
        )

    message = build_message(
        now=now,
        execution_signal=execution_signal,
        downgraded=downgraded,
        advice=advice,
        feasibility=feasibility,
        effective_risk_pct=effective_risk_pct,
    )

    print("\n--- MESSAGE PREVIEW ---")
    try:
        print(message)
    except UnicodeEncodeError:
        print(message.encode("ascii", errors="replace").decode("ascii"))
    print("-----------------------\n")

    include_wait = os.environ.get("INCLUDE_WAIT_SIGNALS", "false").lower() == "true"
    if execution_signal == "WAIT" and not include_wait:
        print("[run_bot] Signal is WAIT, skipping Telegram send.")
    else:
        send_telegram(message)


if __name__ == "__main__":
    main()
