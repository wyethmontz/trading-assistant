from __future__ import annotations

from datetime import datetime, timedelta, timezone

import requests

CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
HIGH_IMPACT_CURRENCIES = {"USD"}

# Well-known high-impact USD indicators where a HIGHER actual-vs-forecast reading is
# hawkish (signals a stronger economy -> USD up -> gold down). False means the
# opposite (e.g. a higher unemployment/claims reading is a weak-economy, dovish,
# gold-positive surprise). Anything not listed here gets no directional read.
EVENT_HAWKISH_ON_HIGHER = {
    "non-farm employment change": True,
    "adp non-farm employment change": True,
    "retail sales m/m": True,
    "core retail sales m/m": True,
    "ism manufacturing pmi": True,
    "ism services pmi": True,
    "s&p global manufacturing pmi": True,
    "s&p global services pmi": True,
    "cpi m/m": True,
    "cpi y/y": True,
    "core cpi m/m": True,
    "core cpi y/y": True,
    "pce price index m/m": True,
    "core pce price index m/m": True,
    "gdp q/q": True,
    "unemployment rate": False,
    "initial jobless claims": False,
    "continuing jobless claims": False,
}


def _parse_numeric(raw: str | None) -> float | None:
    if not raw:
        return None
    text = str(raw).strip().replace("%", "").replace(",", "")
    if not text:
        return None
    multiplier = 1.0
    suffix = text[-1:].upper()
    if suffix in ("K", "M", "B"):
        multiplier = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}[suffix]
        text = text[:-1]
    try:
        return float(text) * multiplier
    except ValueError:
        return None


def _fetch_calendar() -> list[dict]:
    try:
        response = requests.get(CALENDAR_URL, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        events = response.json()
        return events if isinstance(events, list) else []
    except Exception:
        return []


def _parse_event_time(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def get_high_impact_blackout(
    now: datetime,
    before_minutes: float = 60.0,
    after_minutes: float = 60.0,
) -> tuple[bool, str]:
    """Check whether `now` falls near a high-impact USD economic event (NFP, CPI, FOMC, etc).

    Uses ForexFactory's free weekly calendar feed. Fails open (no blackout) if the
    feed can't be fetched or parsed, so a network hiccup never silently blocks
    every signal the way a hard dependency would.
    """
    for event in _fetch_calendar():
        if event.get("impact") != "High" or event.get("country") not in HIGH_IMPACT_CURRENCIES:
            continue

        event_time = _parse_event_time(event.get("date"))
        if event_time is None:
            continue

        window_start = event_time - timedelta(minutes=before_minutes)
        window_end = event_time + timedelta(minutes=after_minutes)
        if window_start <= now <= window_end:
            title = event.get("title", "High-impact economic event")
            return True, f"{title} at {event_time.strftime('%Y-%m-%d %H:%M UTC')}"

    return False, ""


def get_news_driven_bias(now: datetime, after_minutes: float = 60.0) -> tuple[str | None, str]:
    """Read a directional bias from a just-released high-impact USD event's surprise.

    Only looks at events that have already happened (actual value published) within
    `after_minutes`, and only for indicators in `EVENT_HAWKISH_ON_HIGHER` where the
    hawkish/dovish direction is well established. Returns (direction, explanation)
    where direction is "SELL" for a hawkish/gold-negative surprise, "BUY" for a
    dovish/gold-positive one, or (None, "") if nothing recognized/numeric is available.
    """
    for event in _fetch_calendar():
        if event.get("impact") != "High" or event.get("country") not in HIGH_IMPACT_CURRENCIES:
            continue

        title = str(event.get("title", ""))
        higher_is_hawkish = EVENT_HAWKISH_ON_HIGHER.get(title.strip().lower())
        if higher_is_hawkish is None:
            continue

        event_time = _parse_event_time(event.get("date"))
        if event_time is None or event_time > now:
            continue
        if now - event_time > timedelta(minutes=after_minutes):
            continue

        actual = _parse_numeric(event.get("actual"))
        forecast = _parse_numeric(event.get("forecast"))
        if actual is None or forecast is None or actual == forecast:
            continue

        beat_forecast = actual > forecast
        hawkish = beat_forecast if higher_is_hawkish else not beat_forecast
        direction = "SELL" if hawkish else "BUY"
        tone = "hawkish" if hawkish else "dovish"
        explanation = f"{title}: actual {event.get('actual')} vs forecast {event.get('forecast')} ({tone} surprise for USD)"
        return direction, explanation

    return None, ""
