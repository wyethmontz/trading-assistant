# Gold Trading Assistant

A lightweight trading assistant focused on Gold (XAUUSD proxy via `GC=F`) with:

- Real-time OHLC data pull from Yahoo Finance
- Candlestick chart with SMA20 and SMA50 overlays
- RSI and ATR-based setup detection
- Rule-based BUY / SELL / WAIT signal
- Simple risk and position size estimation
- Cross-asset macro dashboard (DXY, US10Y, VIX, Oil, Silver, S&P 500)
- Weighted macro bias score to estimate directional pressure on gold
- Live Gold ticker-linked headline feed
- Event risk checklist for high-impact macro sessions
- External macro news feeds (Reuters/MarketWatch/FXStreet RSS)
- XM broker guardrails (lot step, min lot, spread-aware risk feasibility)
- Adaptive loss review journal that tightens risk/confidence after drawdowns

## XM Setup Notes

Before using live funds, set these exactly from your MT5 Symbol Specification:

- Contract size (oz per 1.00 lot)
- Minimum lot
- Lot step
- Maximum lot
- Typical spread

The app will downgrade a trade to `WAIT` when:

- The position is not feasible at your risk cap
- Confidence is below the active floor
- Adaptive mode detects a losing streak and source misalignment

## Journal Workflow

After each trade closes:

1. Log outcome (Win/Loss/Breakeven)
2. Log actual PnL
3. Add a short note

The app analyzes recent closed trades and automatically recommends tighter risk and higher confidence thresholds after losses.

## Quick Start

1. Create and activate a virtual environment:

   **Windows (PowerShell):**
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

2. Install dependencies:

   ```powershell
   pip install -r requirements.txt
   ```

3. Run the app:

   ```powershell
   streamlit run app.py
   ```

## Notes

- Data symbol: `GC=F` (COMEX Gold Futures proxy).
- The assistant is educational and not financial advice.
- Always confirm signals with your own analysis and broker constraints.

## Automated Signal Bot

`run_bot.py` runs the same advisor pipeline headless (Swing 1h data, macro/news guardrails, adaptive journal risk cap) and sends the resulting signal to Telegram. It only ever notifies — it never places trades.

### Run locally

```powershell
$env:TELEGRAM_BOT_TOKEN = "your_bot_token"
$env:TELEGRAM_CHAT_ID = "your_chat_id"
python run_bot.py
```

### Environment Variables

| Variable | Description | Default |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Bot token from BotFather | required to send |
| `TELEGRAM_CHAT_ID` | Target chat/channel id | required to send |
| `ACCOUNT_BALANCE` | Account balance in USD | `64.18` |
| `RISK_PCT` | Risk per trade (%) | `0.5` |
| `CONFIDENCE_FLOOR` | Minimum confidence to act on a signal | `65` |
| `ADAPTIVE_MODE` | Tighten risk/confidence after a loss streak | `true` |
| `XM_SYMBOL`, `CONTRACT_SIZE`, `MIN_LOT`, `LOT_STEP`, `MAX_LOT`, `SPREAD_USD` | Broker guardrail specs | match XM defaults in `app.py` |

### Automated schedule

Same pattern as `fuel-forecast-bot-py`: [.github/workflows/signal.yml](.github/workflows/signal.yml) exposes a `workflow_dispatch` trigger, and [cron-job.org](https://cron-job.org) calls it hourly via the GitHub Actions API. Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` as repo secrets, and optionally `ACCOUNT_BALANCE` / `RISK_PCT` as repo variables, before enabling the schedule.

### Run with Docker

```bash
docker build -t gold-signal-bot .
docker run -e TELEGRAM_BOT_TOKEN=your_bot_token -e TELEGRAM_CHAT_ID=your_chat_id gold-signal-bot
```
