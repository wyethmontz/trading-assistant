# Trading Assistant Notes

This file is the persistent running log for strategy decisions, setup rules, losses, and adjustments.

## Workflow Rule

- Add a new entry for every meaningful trading update.
- Save to local git and push to GitHub immediately after each update.
- Keep entries short, factual, and actionable.

## Current Preferences

- User trades Gold on XM.
- Prefer 1H confirmation and avoid mid-range entries.
- Notify only when setup quality is very high confidence.

## Entries

### 2026-08-19

- Initialized notes workflow in repo.
- Added multi-source analysis focus: DXY, US10Y yields, VIX, oil, silver, S&P 500, and news context.
- Enforced risk-first behavior for small account sizing and minimum lot constraints.
- [2026-08-20 00:00] Paper BUY session record: BUY trigger confirmed above 4493.5; entry zone 4492.8-4493.6; SL 4489.8; TP 4498.5/4502.0; invalidate on 1H close below 4491.8; status: no valid SELL setup logged.
- [2026-08-20 00:00] Continuation note: next session should resume with BUY-only bias until a fresh 1H confirmation or a clean invalidation. No paper SELL trade exists for this session.

### 2026-08-20

- Added safe grid playbook in SAFE_GRID_RULES.md: max 3 layers, 3.0-dollar spacing, 2.5% basket hard stop, and kill-switch rules.
- Session continuity lock: paper trade state remains BUY from the prior session; reopen only after checking 1H candle at 2026-08-20 10:00 UTC+3 or on a clean invalidation below 4489.8.
