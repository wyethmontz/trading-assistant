from datetime import datetime, timedelta, timezone

import pandas as pd

from src.key_levels import (
    KeyLevels,
    _find_last_swing,
    _prior_period_high_low,
    _round_numbers_straddling,
    _round_step,
    compute_key_levels,
)


def _hourly_index(n: int, start: datetime = datetime(2026, 8, 1, tzinfo=timezone.utc)) -> pd.DatetimeIndex:
    return pd.DatetimeIndex([start + timedelta(hours=i) for i in range(n)])


def _flat_df(n: int, price: float = 100.0) -> pd.DataFrame:
    return pd.DataFrame(
        {"Open": price, "High": price, "Low": price, "Close": price},
        index=_hourly_index(n),
    )


# --- Swing detection ---------------------------------------------------------


def test_swing_high_finds_most_recent_confirmed_pivot():
    highs = [100, 101, 102, 103, 104, 105, 104, 103, 102, 101, 200, 101, 102, 103, 104, 105]
    #                                                    ^ index 10, needs 5 bars after it (indices 11-15) -> confirmed
    series = pd.Series(highs)
    result = _find_last_swing(series, n=5, mode="high")
    assert result == 200.0


def test_swing_low_finds_most_recent_confirmed_pivot():
    lows = [100, 99, 98, 97, 96, 95, 96, 97, 98, 99, 10, 99, 98, 97, 96, 95]
    series = pd.Series(lows)
    result = _find_last_swing(series, n=5, mode="low")
    assert result == 10.0


def test_swing_excludes_unconfirmed_trailing_bars():
    # The extreme sits in the last 5 bars, which can't be confirmed yet (no bars after them).
    highs = [100, 101, 100, 101, 100, 101, 100, 101, 100, 101, 100, 999]
    series = pd.Series(highs)
    result = _find_last_swing(series, n=5, mode="high")
    # 999 (last index) is unconfirmable; nothing else in range is a strict 5-bar-both-sides extreme.
    assert result != 999.0


def test_too_short_series_returns_no_swing():
    # Need at least 2n+1 = 11 bars for n=5; give it fewer.
    series = pd.Series([100, 101, 102, 103, 104, 105, 104])
    assert _find_last_swing(series, n=5, mode="high") is None
    assert _find_last_swing(series, n=5, mode="low") is None


# --- Prior day / week boundaries ---------------------------------------------


def test_prior_day_high_low_excludes_in_progress_day():
    start = datetime(2026, 8, 1, 0, tzinfo=timezone.utc)
    rows = []
    index = []
    # Day 1 (complete): Aug 1, 00:00-23:00
    for h in range(24):
        index.append(start + timedelta(hours=h))
        rows.append({"High": 110.0 if h == 12 else 105.0, "Low": 95.0 if h == 3 else 100.0})
    # Day 2 (in progress): Aug 2, 00:00-05:00
    for h in range(6):
        index.append(start + timedelta(days=1, hours=h))
        rows.append({"High": 500.0, "Low": 1.0})  # extreme values that must NOT be picked up

    df = pd.DataFrame(rows, index=pd.DatetimeIndex(index))
    result = _prior_period_high_low(df, "D")
    assert result == (110.0, 95.0)


def test_prior_week_high_low_excludes_in_progress_week():
    # Two full ISO weeks plus a partial third (in-progress) week.
    start = datetime(2026, 8, 3, tzinfo=timezone.utc)  # a Monday
    index = []
    rows = []
    for day in range(21):  # 3 weeks of daily bars
        ts = start + timedelta(days=day)
        index.append(ts)
        if 7 <= day < 14:  # second week is the "prior completed" week we expect
            rows.append({"High": 999.0, "Low": 1.0})
        elif day >= 14:  # third week: in progress, must be excluded even if extreme
            rows.append({"High": 5000.0, "Low": 0.01})
        else:
            rows.append({"High": 200.0, "Low": 100.0})

    df = pd.DataFrame(rows, index=pd.DatetimeIndex(index))
    result = _prior_period_high_low(df, "W")
    assert result == (999.0, 1.0)


def test_prior_period_returns_none_when_only_one_period_present():
    df = _flat_df(5)  # all within the same single hour-window/day
    assert _prior_period_high_low(df, "D") is None
    assert _prior_period_high_low(df, "W") is None


def test_prior_period_returns_none_for_empty_dataframe():
    df = pd.DataFrame({"High": [], "Low": []}, index=pd.DatetimeIndex([]))
    assert _prior_period_high_low(df, "D") is None


# --- Round numbers -------------------------------------------------------------


def test_round_step_scales_with_price_magnitude():
    assert _round_step(15000) == 500.0
    assert _round_step(4432) == 100.0
    assert _round_step(432) == 10.0
    assert _round_step(43.2) == 1.0
    assert _round_step(4.32) == 0.10
    assert _round_step(0.432) == 0.01


def test_round_numbers_straddle_price_in_normal_case():
    below, above = _round_numbers_straddling(4432.10)
    assert below == 4400.0
    assert above == 4500.0


def test_round_numbers_price_exactly_on_a_level():
    # 4400 sits exactly on a $100 grid line -> must not return itself as either side.
    below, above = _round_numbers_straddling(4400.0)
    assert below == 4300.0
    assert above == 4500.0
    assert below < 4400.0 < above


def test_round_numbers_price_exactly_on_a_level_small_step():
    # 5.0 sits exactly on the $1 grid for the 10-99 tier's neighbor; check the <10 tier's own step (0.10).
    below, above = _round_numbers_straddling(5.10)
    assert below == 5.0
    assert above == 5.2


# --- End-to-end / graceful omission -------------------------------------------


def test_compute_key_levels_omits_prior_week_with_short_history():
    # Only a few hours of data: no swing, no prior day, no prior week possible.
    df = _flat_df(3, price=100.0)
    levels = compute_key_levels(df, current_price=100.5, swing_lookback=5)

    assert isinstance(levels, KeyLevels)
    assert levels.swing_high is None
    assert levels.swing_low is None
    assert levels.prior_day_high is None
    assert levels.prior_week_high is None
    # Round numbers don't depend on candle history, so they're always available.
    assert levels.round_number_below is not None
    assert levels.round_number_above is not None


def test_compute_key_levels_with_enough_history_fills_everything():
    n = 24 * 21  # 3 weeks of hourly data
    # Strictly increasing baseline (no ties anywhere) so the injected spike, which
    # dwarfs the entire baseline range, is an unambiguous local (and global) extreme.
    highs = [100.0 + i * 0.001 for i in range(n)]
    lows = [h - 1.0 for h in highs]
    df = pd.DataFrame({"High": highs, "Low": lows}, index=_hourly_index(n))
    # Inject a clean swing high in the middle, far from both edges.
    df.iloc[200, df.columns.get_loc("High")] = 250.0

    levels = compute_key_levels(df, current_price=100.5, swing_lookback=5)

    assert levels.swing_high == 250.0
    assert levels.prior_day_high is not None
    assert levels.prior_day_low is not None
    assert levels.prior_week_high is not None
    assert levels.prior_week_low is not None
