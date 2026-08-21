from __future__ import annotations

import os

import requests


TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"


def send_telegram(message: str) -> None:
    """Send a message to the configured Telegram chat. No-ops with a warning if unset."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    if not token or not chat_id:
        print("[notifier] TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set, skipping send.")
        return

    url = TELEGRAM_API_URL.format(token=token)
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}

    try:
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()
        print("[notifier] Signal sent to Telegram.")
    except requests.exceptions.RequestException as exc:
        print(f"[notifier] Telegram send failed: {exc}")
        if exc.response is not None:
            print(f"[notifier] Telegram response body: {exc.response.text}")
