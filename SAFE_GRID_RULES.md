# Safe Grid Rules (Gold)

Use this as a safer version of repeated 0.01 buy/sell entries.

## Setup Filters

- Trade only with 1D trend direction.
- Execute only on 1H candle close, not mid-candle.
- Skip during major USD news windows (CPI, NFP, FOMC).

## Entry Structure

- Max layers: 3 positions only.
- Base size: 0.01 lot per layer.
- Add-on spacing: at least 3.0 dollars from last entry.
- Add only if structure still valid on 1H close.

## Basket Controls

- Hard basket stop: close all if total floating loss reaches 2.5% of equity.
- Daily stop: stop trading for the day after 2 consecutive losing baskets.
- Never open a new basket while another basket is active.

## Exit Rules

- Partial take-profit: close 50% at +1.0R basket value.
- Final take-profit: close remainder at +2.0R basket value.
- Time stop: close basket if no progress after 6 closed 1H candles.

## Kill Switch (Must Close All)

- 1H close breaks invalidation level for the trend setup.
- Spread spikes above normal session average.
- News shock candle greater than 1.5x 1H ATR against basket direction.

## Simple Checklist

- Trend aligned?
- Entry at 1H close only?
- Layer count less than or equal to 3?
- Basket risk below 2.5% equity?
- No high-impact news soon?
