from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

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
    effective_entry: float,
    contract_size_oz_per_lot: float,
) -> str:
    signal_line = f"<b>Signal: {execution_signal}</b>"
    if downgraded:
        signal_line += " (downgraded from advisor by guardrails)"

    price_label = f"{execution_signal.capitalize()} When Price is" if execution_signal != "WAIT" else "Reference Price"

    display_take_profit = advice.take_profit

    # `effective_entry` is the price the order is worked at (advisor close + entry buffer).
    # Every derived number below is measured from it, and the position size / risk were
    # sized off it too, so the whole message describes one coherent trade.
    stop_distance = abs(effective_entry - advice.stop_loss)
    target_distance = abs(display_take_profit - effective_entry)

    lots = feasibility.rounded_lots
    size_oz = lots * contract_size_oz_per_lot

    if feasibility.tradable:
        risk_line = f"Risk: ${feasibility.effective_risk_usd:,.2f} ({feasibility.effective_risk_pct:.2f}%)"
    else:
        risk_line = f"Not placeable within risk cap — {feasibility.reason}"

    display_time = now + timedelta(hours=3)

    message = (
        f"<b>Gold Signal — {display_time.strftime('%Y-%m-%d %H:%M')} UTC+3</b>\n\n"
        f"{signal_line}\n"
        f"Trend: {advice.trend} | Confidence: {advice.confidence}%\n\n"
        f"Lot(s): {lots:.2f}\n"
        f"{price_label}: ${effective_entry:,.2f}\n"
        f"Take Profit Level: ${display_take_profit:,.2f}\n"
        f"Stop Loss Level: ${advice.stop_loss:,.2f}\n"
        f"Entry - SL: ${stop_distance:,.2f}\n"
        f"TP - Entry: ${target_distance:,.2f}\n\n"
        f"{risk_line}\n"
        f"Suggested Size: {size_oz:,.2f} oz"
    )
    if feasibility.note:
        message += f"\nNote: {feasibility.note}"
    return message


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
    entry_buffer = _env_float("ENTRY_BUFFER_USD", 0.0)

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

    # Shorts (and bearish WAITs) are sized at half risk. Apply it to the risk budget
    # *before* sizing so lots, oz and $ risk in the message all describe one position.
    is_sell_like = advice.action == "SELL" or (advice.action == "WAIT" and advice.trend == "Bearish")
    sizing_risk_pct = effective_risk_pct * 0.5 if is_sell_like else effective_risk_pct

    # The order is worked `entry_buffer` above the advisor close (both directions, per
    # the tuned config). Distances, sizing and the logged signal all use this same price.
    effective_entry = advice.entry + entry_buffer if advice.entry > 0 else advice.entry

    feasibility = evaluate_trade_feasibility(
        account_balance=account_balance,
        risk_pct=sizing_risk_pct,
        entry=effective_entry,
        stop=advice.stop_loss,
        spec=spec,
        max_risk_pct=effective_risk_pct,
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
            entry=effective_entry,
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
        effective_entry=effective_entry,
        contract_size_oz_per_lot=contract_size,
    )

    print("\n--- MESSAGE PREVIEW ---")
    try:
        print(message)
    except UnicodeEncodeError:
        print(message.encode("ascii", errors="replace").decode("ascii"))
    print("-----------------------\n")

    include_wait = os.environ.get("INCLUDE_WAIT_SIGNALS", "true").lower() == "true"
    only_send_buy = os.environ.get("ONLY_SEND_BUY", "true").lower() == "true"

    if only_send_buy and execution_signal != "BUY":
        print(f"[run_bot] ONLY_SEND_BUY is enabled and signal is {execution_signal}, skipping Telegram send.")
    elif execution_signal == "WAIT" and not include_wait:
        print("[run_bot] Signal is WAIT, skipping Telegram send.")
    else:
        send_telegram(message)


if __name__ == "__main__":
    main()
