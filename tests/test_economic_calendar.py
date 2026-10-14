from datetime import datetime, timedelta, timezone

from src import economic_calendar


def _event(title: str, when: datetime, impact: str = "High", country: str = "USD") -> dict:
    return {
        "title": title,
        "country": country,
        "impact": impact,
        "date": when.isoformat().replace("+00:00", "Z"),
    }


def test_no_upcoming_event_returns_empty(monkeypatch):
    monkeypatch.setattr(economic_calendar, "_fetch_calendar", lambda: [])
    now = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)
    assert economic_calendar.get_next_high_impact_event(now=now) == ""


def test_finds_event_within_horizon(monkeypatch):
    now = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)
    event_time = now + timedelta(hours=5, minutes=30)
    monkeypatch.setattr(economic_calendar, "_fetch_calendar", lambda: [_event("CPI m/m", event_time)])

    result = economic_calendar.get_next_high_impact_event(now=now, within_hours=24.0)
    assert "CPI m/m" in result
    assert "in 5h 30m" in result


def test_excludes_event_past_horizon(monkeypatch):
    now = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)
    event_time = now + timedelta(hours=30)
    monkeypatch.setattr(economic_calendar, "_fetch_calendar", lambda: [_event("FOMC", event_time)])

    assert economic_calendar.get_next_high_impact_event(now=now, within_hours=24.0) == ""


def test_excludes_past_event(monkeypatch):
    now = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)
    event_time = now - timedelta(minutes=5)
    monkeypatch.setattr(economic_calendar, "_fetch_calendar", lambda: [_event("NFP", event_time)])

    assert economic_calendar.get_next_high_impact_event(now=now) == ""


def test_excludes_low_impact_and_non_usd(monkeypatch):
    now = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)
    events = [
        _event("MX Unemployment", now + timedelta(hours=1), country="MXN"),
        _event("Low impact release", now + timedelta(hours=1), impact="Low"),
    ]
    monkeypatch.setattr(economic_calendar, "_fetch_calendar", lambda: events)

    assert economic_calendar.get_next_high_impact_event(now=now) == ""


def test_picks_soonest_of_multiple_events(monkeypatch):
    now = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)
    events = [
        _event("PPI m/m", now + timedelta(hours=10)),
        _event("NFP", now + timedelta(hours=2)),
    ]
    monkeypatch.setattr(economic_calendar, "_fetch_calendar", lambda: events)

    result = economic_calendar.get_next_high_impact_event(now=now)
    assert "NFP" in result
    assert "PPI" not in result
