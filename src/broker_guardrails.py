from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass
class BrokerSpec:
    symbol: str
    contract_size_oz_per_lot: float
    min_lot: float
    lot_step: float
    max_lot: float
    spread_usd: float


@dataclass
class FeasibilityResult:
    tradable: bool
    reason: str
    suggested_lots: float
    rounded_lots: float
    effective_risk_usd: float
    effective_risk_pct: float
    note: str = ""


def _round_down_to_step(value: float, step: float) -> float:
    if step <= 0:
        return value
    return math.floor(value / step) * step


def evaluate_trade_feasibility(
    account_balance: float,
    risk_pct: float,
    entry: float,
    stop: float,
    spec: BrokerSpec,
    max_risk_pct: float | None = None,
) -> FeasibilityResult:
    """`risk_pct` is the target sizing budget (may be reduced, e.g. half-size for shorts).
    `max_risk_pct` is the hard ceiling that must not be breached; when the target size
    rounds below the broker minimum lot we fall back to the minimum lot only if its real
    risk still fits under this ceiling. Defaults to `risk_pct` when not given."""
    risk_budget_usd = account_balance * (risk_pct / 100)
    ceiling_pct = max_risk_pct if max_risk_pct is not None else risk_pct
    risk_per_oz = abs(entry - stop)

    if risk_per_oz <= 0:
        return FeasibilityResult(
            tradable=False,
            reason="Invalid stop distance.",
            suggested_lots=0.0,
            rounded_lots=0.0,
            effective_risk_usd=0.0,
            effective_risk_pct=0.0,
        )

    all_in_risk_per_lot = (risk_per_oz + max(spec.spread_usd, 0.0)) * spec.contract_size_oz_per_lot
    if all_in_risk_per_lot <= 0:
        return FeasibilityResult(
            tradable=False,
            reason="Invalid broker specification.",
            suggested_lots=0.0,
            rounded_lots=0.0,
            effective_risk_usd=0.0,
            effective_risk_pct=0.0,
        )

    suggested = risk_budget_usd / all_in_risk_per_lot
    rounded = _round_down_to_step(suggested, spec.lot_step)
    rounded = min(max(rounded, 0.0), spec.max_lot)

    if rounded < spec.min_lot:
        min_lot_risk = spec.min_lot * all_in_risk_per_lot
        min_lot_risk_pct = (min_lot_risk / account_balance) * 100 if account_balance > 0 else 0.0
        if spec.min_lot <= spec.max_lot and min_lot_risk_pct <= ceiling_pct:
            return FeasibilityResult(
                tradable=True,
                reason="Position size is within broker limits and your risk cap.",
                suggested_lots=suggested,
                rounded_lots=spec.min_lot,
                effective_risk_usd=min_lot_risk,
                effective_risk_pct=min_lot_risk_pct,
                note=(
                    f"Target size {suggested:.4f} lot is below broker minimum "
                    f"{spec.min_lot:.2f} - using minimum lot; real risk "
                    f"${min_lot_risk:.2f} ({min_lot_risk_pct:.2f}%)."
                ),
            )
        return FeasibilityResult(
            tradable=False,
            reason=(
                f"Minimum lot {spec.min_lot:.2f} exceeds your risk cap. "
                f"At minimum lot, risk is about ${min_lot_risk:.2f} ({min_lot_risk_pct:.2f}%)."
            ),
            suggested_lots=suggested,
            rounded_lots=0.0,
            effective_risk_usd=min_lot_risk,
            effective_risk_pct=min_lot_risk_pct,
        )

    effective_risk = rounded * all_in_risk_per_lot
    effective_risk_pct = (effective_risk / account_balance) * 100 if account_balance > 0 else 0.0

    return FeasibilityResult(
        tradable=True,
        reason="Position size is within broker limits and your risk cap.",
        suggested_lots=suggested,
        rounded_lots=rounded,
        effective_risk_usd=effective_risk,
        effective_risk_pct=effective_risk_pct,
    )
