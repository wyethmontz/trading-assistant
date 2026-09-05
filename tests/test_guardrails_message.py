from datetime import datetime, timezone
from types import SimpleNamespace

from src.broker_guardrails import BrokerSpec, evaluate_trade_feasibility
from run_bot import build_message

SPEC = BrokerSpec(
    symbol="XAUUSD",
    contract_size_oz_per_lot=100.0,
    min_lot=0.01,
    lot_step=0.01,
    max_lot=50.0,
    spread_usd=0.5,
)


def test_min_lot_fallback_when_target_below_minimum_but_within_ceiling():
    # Half-size budget rounds below 0.01 lot, but min-lot risk (~0.29%) fits under the 0.50% ceiling.
    result = evaluate_trade_feasibility(
        account_balance=10_000.0,
        risk_pct=0.25,          # halved sizing budget
        entry=4558.92,
        stop=4584.43,
        spec=SPEC,
        max_risk_pct=0.50,      # un-halved ceiling
    )
    assert result.tradable is True
    assert result.rounded_lots == 0.01
    assert result.note  # explains the bump to minimum lot
    assert result.effective_risk_pct <= 0.50


def test_min_lot_still_rejected_when_over_ceiling():
    # Wide stop: even one min lot blows past the ceiling -> not tradable.
    result = evaluate_trade_feasibility(
        account_balance=500.0,
        risk_pct=0.25,
        entry=4558.92,
        stop=4620.0,
        spec=SPEC,
        max_risk_pct=0.50,
    )
    assert result.tradable is False
    assert result.rounded_lots == 0.0


def test_message_numbers_are_consistent():
    advice = SimpleNamespace(
        action="SELL", trend="Bearish", confidence=95,
        entry=4555.92, stop_loss=4584.43, take_profit=4498.89,
    )
    effective_entry = advice.entry + 3.0
    feasibility = evaluate_trade_feasibility(
        account_balance=10_000.0, risk_pct=0.25,
        entry=effective_entry, stop=advice.stop_loss, spec=SPEC, max_risk_pct=0.50,
    )
    msg = build_message(
        now=datetime(2026, 8, 28, 14, 5, tzinfo=timezone.utc),
        execution_signal="SELL", downgraded=False, advice=advice,
        feasibility=feasibility, effective_entry=effective_entry,
        contract_size_oz_per_lot=SPEC.contract_size_oz_per_lot,
    )
    # Lot(s) x contract size must equal the Suggested Size oz shown.
    lots = feasibility.rounded_lots
    assert f"Lot(s): {lots:.2f}" in msg
    assert f"Suggested Size: {lots * 100:,.2f} oz" in msg
    # Entry shown is the buffered entry, and the distances are measured from it.
    assert f"${effective_entry:,.2f}" in msg
    assert f"Entry - SL: ${abs(effective_entry - advice.stop_loss):,.2f}" in msg
    assert f"TP - Entry: ${abs(advice.take_profit - effective_entry):,.2f}" in msg


def test_message_flags_not_placeable():
    advice = SimpleNamespace(
        action="SELL", trend="Bearish", confidence=95,
        entry=4555.92, stop_loss=4700.0, take_profit=4400.0,
    )
    feasibility = evaluate_trade_feasibility(
        account_balance=300.0, risk_pct=0.25,
        entry=advice.entry, stop=advice.stop_loss, spec=SPEC, max_risk_pct=0.50,
    )
    msg = build_message(
        now=datetime(2026, 8, 28, 14, 5, tzinfo=timezone.utc),
        execution_signal="WAIT", downgraded=True, advice=advice,
        feasibility=feasibility, effective_entry=advice.entry + 3.0,
        contract_size_oz_per_lot=SPEC.contract_size_oz_per_lot,
    )
    assert "Not placeable within risk cap" in msg


def test_sell_take_profit_buffer_never_crosses_entry():
    # Low ATR -> raw target is closer to entry than the +$30 buffer, which would
    # otherwise push the displayed Take Profit past entry (onto the losing side).
    entry = 4431.47
    stop_loss = 4441.44  # 1.5x ATR above entry
    atr = (stop_loss - entry) / 1.5
    raw_take_profit = entry - 3 * atr  # 3x ATR below entry
    advice = SimpleNamespace(action="SELL", trend="Bearish", confidence=95, entry=entry, stop_loss=stop_loss, take_profit=raw_take_profit)

    feasibility = evaluate_trade_feasibility(
        account_balance=10_000.0, risk_pct=0.25,
        entry=entry, stop=stop_loss, spec=SPEC, max_risk_pct=0.50,
    )
    msg = build_message(
        now=datetime(2026, 9, 5, 14, 31, tzinfo=timezone.utc),
        execution_signal="SELL", downgraded=False, advice=advice,
        feasibility=feasibility, effective_entry=entry,
        contract_size_oz_per_lot=SPEC.contract_size_oz_per_lot,
        sell_take_profit_buffer=30.0,
    )
    assert f"Sell When Price is: ${entry:,.2f}" in msg
    # The buffered/uncapped target would have been entry + 10.06 (the reported bug);
    # capped, it must land strictly below entry instead.
    displayed_tp = float(msg.split("Take Profit Level: $")[1].split("\n")[0].replace(",", ""))
    assert displayed_tp < entry
