"""Tests for solar_live — the realtime feed behind GET /api/v1/solar/live.

Two halves, deliberately: the streaming loop (frame format, cadence,
termination, first-poll snapshot) against a fake poll, and the poll logic
against a live database with the same fixture pattern as
test_solar_insights.py. Only the latter needs Postgres, so the marker is per
test rather than module-wide — the loop's contract is what a client actually
depends on, and none of it needs a database or a clock to verify.
"""

import json
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from solgrid_tea.schemas.solar import SolarLiveFreshness, SolarLiveTick
from solgrid_tea.services.solar_live import (
    DEFAULT_INTERVAL_S,
    STALE_AFTER_HOURS,
    LiveCursor,
    format_event,
    live_freshness,
    next_live_payloads,
    solar_live_events,
)

PERIOD_START = date(2026, 1, 1)
PERIOD_END = date(2026, 8, 31)
NOW = datetime(2026, 8, 31, 16, 0, tzinfo=timezone.utc)


def _tick(now=NOW) -> SolarLiveTick:
    return SolarLiveTick(
        freshness=SolarLiveFreshness(
            server_ts=now, latest_health_ts=None, latest_health_age_s=None, is_stale=True
        )
    )


def _frames(text_: str) -> list[tuple[str, dict]]:
    parsed = []
    for frame in text_.split("\n\n"):
        if not frame.strip():
            continue
        event_line, data_line = frame.split("\n", 1)
        parsed.append((event_line.removeprefix("event: "), json.loads(data_line[6:])))
    return parsed


# ---------- the streaming loop (no database) ----------


def test_loop_streams_frames_then_stops_at_max_ticks():
    calls: list[dict] = []
    sleeps: list[float] = []

    def poll(cursor, **kwargs):
        calls.append(kwargs)
        return [("tick", _tick())], cursor

    frames = list(
        solar_live_events(
            None,
            "org",
            uuid.uuid4(),
            interval_s=2.5,
            max_ticks=3,
            poll_fn=poll,
            sleep=sleeps.append,
            now_fn=lambda: NOW,
        )
    )

    assert len(frames) == 3
    # Sleeps between ticks, never after the last one — a stream that pauses
    # before handing over its final frame just delays it.
    assert sleeps == [2.5, 2.5]


def test_loop_snapshots_on_the_first_poll_only():
    initials: list[bool] = []

    def poll(cursor, **kwargs):
        initials.append(kwargs["initial"])
        return [("tick", _tick())], cursor

    list(
        solar_live_events(
            None, "org", uuid.uuid4(), max_ticks=3, poll_fn=poll, sleep=lambda _: None
        )
    )

    assert initials == [True, False, False]


def test_loop_passes_the_window_and_the_polled_time_to_each_poll():
    seen: list[dict] = []

    def poll(cursor, **kwargs):
        seen.append(kwargs)
        return [], cursor

    list(
        solar_live_events(
            None,
            "org",
            uuid.uuid4(),
            period_start=PERIOD_START,
            period_end=PERIOD_END,
            max_ticks=2,
            poll_fn=poll,
            sleep=lambda _: None,
            now_fn=lambda: NOW,
        )
    )

    assert [(k["period_start"], k["period_end"], k["now"]) for k in seen] == [
        (PERIOD_START, PERIOD_END, NOW),
        (PERIOD_START, PERIOD_END, NOW),
    ]


def test_loop_defaults_to_a_year_of_history_when_no_window_is_given():
    seen: list[dict] = []

    def poll(cursor, **kwargs):
        seen.append(kwargs)
        return [], cursor

    list(
        solar_live_events(
            None,
            "org",
            uuid.uuid4(),
            max_ticks=1,
            poll_fn=poll,
            sleep=lambda _: None,
            now_fn=lambda: NOW,
        )
    )

    assert seen[0]["period_end"] == date.today()
    assert seen[0]["period_start"] == date(date.today().year - 1, date.today().month, 1)


def test_default_interval_is_a_couple_of_seconds():
    # Guards a real regression: a "live" feed that polls every 30s reads as
    # broken to anyone watching it.
    assert 1 <= DEFAULT_INTERVAL_S <= 10


def test_format_event_is_one_sse_frame():
    frame = format_event("tick", _tick())

    assert frame.startswith("event: tick\ndata: ")
    assert frame.endswith("\n\n")
    # The payload itself must be a single line: an embedded newline would
    # split it across two data lines and an SSE parser would reassemble it
    # with a stray \n — or drop it, depending on the client.
    assert "\n" not in frame.removeprefix("event: tick\ndata: ").removesuffix("\n\n")
    assert _frames(frame)[0][1]["freshness"]["is_stale"] is True


def test_loop_frames_parse_back_as_sse_events():
    frames = list(
        solar_live_events(
            None,
            "org",
            uuid.uuid4(),
            max_ticks=2,
            poll_fn=lambda cursor, **_: ([("tick", _tick())], cursor),
            sleep=lambda _: None,
            now_fn=lambda: NOW,
        )
    )

    assert [name for name, _ in _frames("".join(frames))] == ["tick", "tick"]


# ---------- the poll logic (live database) ----------


@pytest.fixture()
def facility(db_session):
    org_id = uuid.uuid4()
    db_session.execute(
        text("SELECT set_config('app.org_id', :org_id, true)"), {"org_id": str(org_id)}
    )
    db_session.execute(
        text("INSERT INTO organization (id, name) VALUES (:id, 'Solar Live Co')"),
        {"id": str(org_id)},
    )
    facility_id = uuid.uuid4()
    db_session.execute(
        text(
            "INSERT INTO facility (id, organization_id, name, install_capacity_kw) "
            "VALUES (:id, :org_id, 'Live Facility', 100)"
        ),
        {"id": str(facility_id), "org_id": str(org_id)},
    )
    return facility_id


def _add_health_reading(session, facility_id, ts, soc=60.0, soh=95.0):
    session.execute(
        text(
            "INSERT INTO solar_health_reading "
            "(facility_id, ts, battery_soc_pct, battery_soh_pct, panel_status, "
            "battery_status, source_channel) "
            "VALUES (:f, :ts, :soc, :soh, 'normal', 'normal', 'seed')"
        ),
        {"f": str(facility_id), "ts": ts, "soc": soc, "soh": soh},
    )


def _add_generation_reading(session, facility_id, period_start, period_end, quantity):
    session.execute(
        text(
            "INSERT INTO energy_reading "
            "(facility_id, reading_type, period_start, period_end, quantity, unit, source_channel) "
            "VALUES (:f, 'solar_generation', :ps, :pe, :q, 'kWh', 'manual')"
        ),
        {"f": str(facility_id), "ps": period_start, "pe": period_end, "q": quantity},
    )


def _poll(session, facility_id, cursor, *, initial=False, now=NOW):
    return next_live_payloads(
        session,
        facility_id,
        cursor,
        period_start=PERIOD_START,
        period_end=PERIOD_END,
        now=now,
        initial=initial,
    )


def _events(payloads):
    return [name for name, _ in payloads]


@pytest.mark.db
def test_first_poll_snapshots_then_ticks(db_session, facility):
    _add_health_reading(db_session, facility, datetime(2026, 8, 30, 15, tzinfo=timezone.utc))

    payloads, cursor = _poll(db_session, facility, LiveCursor(), initial=True)

    assert _events(payloads) == ["snapshot", "tick"]
    snapshot = payloads[0][1]
    assert snapshot.facility_id == facility
    assert snapshot.health.latest is not None
    assert snapshot.freshness.latest_health_ts == datetime(2026, 8, 30, 15, tzinfo=timezone.utc)
    # The cursor lands on what is already on file, so the next poll has
    # nothing to say about it.
    assert cursor.health_ts == datetime(2026, 8, 30, 15, tzinfo=timezone.utc)


@pytest.mark.db
def test_poll_after_snapshot_does_not_replay_existing_readings(db_session, facility):
    # A month of daily readings, established as the baseline...
    for day in range(1, 31):
        _add_health_reading(db_session, facility, datetime(2026, 8, day, 15, tzinfo=timezone.utc))

    _, cursor = _poll(db_session, facility, LiveCursor(), initial=True)
    payloads, _ = _poll(db_session, facility, cursor)

    # ...so a poll with nothing new sends only the heartbeat.
    assert _events(payloads) == ["tick"]


@pytest.mark.db
def test_poll_sends_only_readings_newer_than_the_cursor(db_session, facility):
    _add_health_reading(db_session, facility, datetime(2026, 8, 28, 15, tzinfo=timezone.utc))
    _, cursor = _poll(db_session, facility, LiveCursor(), initial=True)

    _add_health_reading(
        db_session, facility, datetime(2026, 8, 29, 15, tzinfo=timezone.utc), soc=71.0
    )
    _add_health_reading(
        db_session, facility, datetime(2026, 8, 30, 15, tzinfo=timezone.utc), soc=74.0
    )

    payloads, cursor = _poll(db_session, facility, cursor)

    assert _events(payloads) == ["health", "tick"]
    points = payloads[0][1].points
    assert [p.ts for p in points] == [
        datetime(2026, 8, 29, 15, tzinfo=timezone.utc),
        datetime(2026, 8, 30, 15, tzinfo=timezone.utc),
    ]
    assert [p.battery_soc_pct for p in points] == [71.0, 74.0]
    assert cursor.health_ts == datetime(2026, 8, 30, 15, tzinfo=timezone.utc)

    # And the same poll again is quiet — the cursor advanced with what it sent.
    payloads, _ = _poll(db_session, facility, cursor)
    assert _events(payloads) == ["tick"]


@pytest.mark.db
def test_health_update_carries_a_summary_including_the_new_reading(db_session, facility):
    _add_health_reading(
        db_session, facility, datetime(2026, 8, 28, 15, tzinfo=timezone.utc), soh=95.0
    )
    _, cursor = _poll(db_session, facility, LiveCursor(), initial=True)

    _add_health_reading(
        db_session, facility, datetime(2026, 8, 29, 15, tzinfo=timezone.utc), soh=80.0
    )
    payloads, _ = _poll(db_session, facility, cursor)

    update = payloads[0][1]
    assert update.health.latest.battery_soh_pct == 80.0
    assert any(i.severity == "warn" for i in update.health.insights)


@pytest.mark.db
def test_health_summary_reflects_readings_after_the_ledger_window(db_session, facility):
    # A live reading landing weeks after the ledger's last billing month —
    # exactly the normal case, since ledger periods are monthly and a live
    # feed keeps going. `health.latest` must be computed as of *now*, not
    # capped to period_end, or every live reading would look invisible.
    _add_health_reading(db_session, facility, datetime(2026, 8, 30, 15, tzinfo=timezone.utc))
    _, cursor = _poll(db_session, facility, LiveCursor(), initial=True)

    live_ts = datetime(2026, 9, 18, 10, 0, tzinfo=timezone.utc)
    _add_health_reading(db_session, facility, live_ts, soc=91.0)

    payloads, _ = _poll(db_session, facility, cursor, now=live_ts + timedelta(minutes=1))

    update = payloads[0][1]
    assert update.health.latest.ts == live_ts
    assert update.health.latest.battery_soc_pct == 91.0


@pytest.mark.db
def test_series_is_sent_when_generation_rows_appear_and_not_otherwise(db_session, facility):
    _add_health_reading(db_session, facility, datetime(2026, 8, 30, 15, tzinfo=timezone.utc))
    _, cursor = _poll(db_session, facility, LiveCursor(), initial=True)

    payloads, cursor = _poll(db_session, facility, cursor)
    assert _events(payloads) == ["tick"]

    _add_generation_reading(db_session, facility, date(2026, 8, 1), date(2026, 8, 31), 4200)
    payloads, cursor = _poll(db_session, facility, cursor)

    assert _events(payloads) == ["series", "tick"]
    points = payloads[0][1].series.points
    assert len(points) == 1
    assert points[0].generation_kwh == 4200

    # Re-sent once, then left alone.
    payloads, _ = _poll(db_session, facility, cursor)
    assert _events(payloads) == ["tick"]


@pytest.mark.db
def test_series_is_resent_when_a_new_ledger_period_lands_mid_stream(db_session, facility):
    # A month rollover while a dashboard is open: the chart would be missing
    # the new month forever if the marker only tracked row counts.
    _add_health_reading(db_session, facility, datetime(2026, 7, 31, 15, tzinfo=timezone.utc))
    _, cursor = _poll(db_session, facility, LiveCursor(), initial=True)

    _add_generation_reading(db_session, facility, date(2026, 8, 1), date(2026, 8, 31), 5000)
    payloads, _ = _poll(db_session, facility, cursor)

    assert _events(payloads) == ["series", "tick"]


@pytest.mark.db
def test_freshness_reports_age_and_staleness(db_session, facility):
    fresh = NOW - timedelta(hours=2)
    _add_health_reading(db_session, facility, fresh)

    freshness = live_freshness(db_session, facility, NOW)

    assert freshness.latest_health_ts == fresh
    assert freshness.latest_health_age_s == pytest.approx(2 * 3600)
    assert freshness.is_stale is False

    stale = live_freshness(db_session, facility, NOW + timedelta(hours=STALE_AFTER_HOURS + 1))
    assert stale.is_stale is True


@pytest.mark.db
def test_freshness_with_no_readings_at_all_is_stale_not_missing(db_session, facility):
    freshness = live_freshness(db_session, facility, NOW)

    assert freshness.latest_health_ts is None
    assert freshness.latest_health_age_s is None
    # A site that has never reported is the most stale case there is, not a
    # "no opinion" one — the UI has to be able to say so.
    assert freshness.is_stale is True
