from __future__ import annotations

from datetime import datetime, timedelta, timezone

import requests

CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
HIGH_IMPACT_CURRENCIES = {"USD"}


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


def get_next_high_impact_event(now: datetime, within_hours: float = 24.0) -> str:
    """Return a note naming the soonest upcoming high-impact USD event within `within_hours`.

    Returns "" if none is found, or the feed can't be fetched/parsed (fails open,
    same as `get_high_impact_blackout`).
    """
    horizon = now + timedelta(hours=within_hours)
    soonest: tuple[datetime, str] | None = None

    for event in _fetch_calendar():
        if event.get("impact") != "High" or event.get("country") not in HIGH_IMPACT_CURRENCIES:
            continue

        event_time = _parse_event_time(event.get("date"))
        if event_time is None or event_time <= now or event_time > horizon:
            continue

        if soonest is None or event_time < soonest[0]:
            soonest = (event_time, event.get("title", "High-impact economic event"))

    if soonest is None:
        return ""

    event_time, title = soonest
    minutes_until = int((event_time - now).total_seconds() // 60)
    hours_until, mins_until = divmod(minutes_until, 60)
    return f"{title} at {event_time.strftime('%Y-%m-%d %H:%M UTC')} (in {hours_until}h {mins_until}m)"
