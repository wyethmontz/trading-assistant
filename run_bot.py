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
from src.signal_tracker import SignalStats, get_signal_stats, log_signal, resolve_open_signals


def _env_float(name: str, default: float) -> float:
    value = os.environ.get(name, "")
    return float(value) if value else default


def build_message(
    now: datetime,
    execution_signal: str,
    downgraded: bool,
    advice,
    feasibility,
    macro_bias: float,
    news_sentiment: float,
    effective_risk_pct: float,
    signal_stats: SignalStats,
) -> str:
    signal_line = f"<b>Signal: {execution_signal}</b>"
    if downgraded:
        signal_line += " (downgraded from advisor by guardrails)"

    feasibility_line = "Feasible at current risk cap." if feasibility.tradable else f"Not feasible: {feasibility.reason}"

    if signal_stats.resolved > 0:
        track_record = (
            f"Track record (all rule calls): {signal_stats.wins}W / {signal_stats.losses}L "
            f"({signal_stats.win_rate:.1f}% win rate), {signal_stats.open_count} still open"
        )
        if signal_stats.actionable_resolved > 0:
            track_record += (
                f"\nOf those, actually tradable at your account size: {signal_stats.actionable_wins}W / "
                f"{signal_stats.actionable_resolved - signal_stats.actionable_wins}L "
                f"({signal_stats.actionable_win_rate:.1f}% win rate)"
            )
    else:
        track_record = f"Track record: no resolved signals yet ({signal_stats.open_count} open)"

    return (
        f"<b>Gold Signal — {now.strftime('%Y-%m-%d %H:%M UTC')}</b>\n\n"
        f"{signal_line}\n"
        f"Trend: {advice.trend} | Confidence: {advice.confidence}%\n"
        f"{advice.notes}\n\n"
        f"Entry: ${advice.entry:,.2f}\n"
        f"Stop Loss: ${advice.stop_loss:,.2f}\n"
        f"Take Profit: ${advice.take_profit:,.2f}\n"
        f"Risk: ${advice.risk_amount:,.2f} ({effective_risk_pct:.2f}%)\n"
        f"Suggested Size: {advice.position_size_oz:,.2f} oz (rounded lots: {feasibility.rounded_lots:.3f})\n\n"
        f"Macro Bias: {macro_bias:+.1f} | News Sentiment: {news_sentiment:+.1f}\n"
        f"{feasibility_line}\n"
        f"{track_record}\n\n"
        f"<i>Educational use only, not financial advice. Confirm against your own analysis.</i>"
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

    signal_interval = os.environ.get("SIGNAL_INTERVAL", "15m")

    print(f"Fetching gold data ({signal_interval} candles)...")
    raw_df = get_gold_data(period="1mo", interval=signal_interval)
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

    signal_stats = get_signal_stats()

    message = build_message(
        now=now,
        execution_signal=execution_signal,
        downgraded=downgraded,
        advice=advice,
        feasibility=feasibility,
        macro_bias=macro_bias,
        news_sentiment=news_sentiment,
        effective_risk_pct=effective_risk_pct,
        signal_stats=signal_stats,
    )

    print("\n--- MESSAGE PREVIEW ---")
    try:
        print(message)
    except UnicodeEncodeError:
        print(message.encode("ascii", errors="replace").decode("ascii"))
    print("-----------------------\n")

    if execution_signal == "WAIT":
        print("[run_bot] Signal is WAIT, skipping Telegram send.")
    else:
        send_telegram(message)


if __name__ == "__main__":
    main()
