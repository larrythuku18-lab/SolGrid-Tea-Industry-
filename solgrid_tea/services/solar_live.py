"""Realtime feed for the Solar page — server-sent events over the same two
tables `solar_insights` reads.

What makes this "realtime" is that it reports what has actually landed, when
it lands: each poll emits whatever `solar_health_reading` rows appeared since
the previous poll, re-emits the generation series only when the rows behind
it changed, and emits a freshness tick on *every* poll whether or not
anything arrived.

That last part is load-bearing rather than filler. There is no device feed in
this system yet (see migrations/0002), so the honest question a live view has
to answer is "is the site still reporting?", and a dashboard that only moves
when data arrives answers it wrongly — it looks identical whether the site is
quiet or dead. `is_stale` comes from the reading cadence the project already
seeds (daily, see `seed-solar-demo`), not from a threshold invented per
viewer, and it is reported rather than smoothed over.

Nothing here synthesizes a reading from a reading. `flask seed-solar-live`
appends real rows on an interval for demos — real rows genuinely arriving,
which is what this stream then delivers.
"""

import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from solgrid_tea.models import EnergyReading, SolarHealthReading
from solgrid_tea.schemas.solar import (
    SolarHealthPoint,
    SolarLiveFreshness,
    SolarLiveHealthUpdate,
    SolarLiveSeriesUpdate,
    SolarLiveSnapshot,
    SolarLiveTick,
)
from solgrid_tea.services.solar_insights import (
    generation_vs_consumption_series,
    solar_health_summary,
)

DEFAULT_INTERVAL_S = 4.0
DEFAULT_LOOKBACK_MONTHS = 12

# The reading types the generation-vs-consumption series reconciles — kept in
# step with solar_insights.generation_vs_consumption_series. diesel's kWh
# equivalent depends on an energy_content_factor row rather than on rows in
# this table, so a newly-published factor won't trip this marker; the series
# is recomputed on every other signal anyway, and minutes-stale by one
# reference row is a far smaller wart than polling for it.
GENERATION_READING_TYPES = ("solar_generation", "grid_electricity", "diesel")

# Seeded readings arrive once a day (see `seed-solar-demo`'s
# _HEALTH_READING_HOUR_UTC). A day and a half of silence is comfortably past
# "today's reading is just late", so flagging it is informative rather than
# noisy.
STALE_AFTER_HOURS = 36.0


@dataclass(frozen=True)
class LiveCursor:
    """Where the last poll looked.

    `health_ts` is the newest `solar_health_reading.ts` already delivered, and
    None means "not established yet" — the first poll baselines it against
    whatever is on file instead of replaying it (see `next_live_payloads`).
    `generation_marker` is a cheap change-detector for the ledger rows behind
    the generation series, so that series is only recomputed and re-sent when
    it can actually differ.
    """

    health_ts: datetime | None = None
    generation_marker: tuple[int, date | None] | None = None


def _set_tenant(session: Session, org_id: str) -> None:
    """app.org_id is set with set_config(..., is_local=true) — scoped to
    exactly one transaction. The stream opens a fresh session per poll rather
    than holding one open for the life of the connection (which would pin a
    pooled connection for as long as a browser tab is left open), so the
    tenant context has to be re-applied on every poll."""
    session.execute(text("SELECT set_config('app.org_id', :org_id, true)"), {"org_id": org_id})


def _generation_marker(
    session: Session, facility_id: UUID, period_start: date, period_end: date
) -> tuple[int, date | None]:
    """Row count + newest period_end over exactly the rows
    `generation_vs_consumption_series` reads for this window. Any change that
    could move a point in that series changes this pair, and a poll that
    doesn't change it skips the recompute (and the re-send) entirely."""
    count, latest = session.execute(
        select(func.count(), func.max(EnergyReading.period_end)).where(
            EnergyReading.facility_id == facility_id,
            EnergyReading.reading_type.in_(GENERATION_READING_TYPES),
            EnergyReading.period_start >= period_start,
            EnergyReading.period_end <= period_end,
        )
    ).one()
    return (int(count), latest)


def live_freshness(
    session: Session, facility_id: UUID, now: datetime | None = None
) -> SolarLiveFreshness:
    now = now or datetime.now(timezone.utc)
    latest_ts = session.scalar(
        select(func.max(SolarHealthReading.ts)).where(SolarHealthReading.facility_id == facility_id)
    )
    age_s = (now - latest_ts).total_seconds() if latest_ts is not None else None
    return SolarLiveFreshness(
        server_ts=now,
        latest_health_ts=latest_ts,
        latest_health_age_s=age_s,
        is_stale=age_s is None or age_s > STALE_AFTER_HOURS * 3600,
    )


def _months_before(value: date, months: int) -> date:
    year, month = value.year, value.month - months
    while month < 1:
        month += 12
        year -= 1
    return date(year, month, 1)


def next_live_payloads(
    session: Session,
    facility_id: UUID,
    cursor: LiveCursor,
    *,
    period_start: date,
    period_end: date,
    now: datetime,
    initial: bool,
) -> tuple[list[tuple[str, BaseModel]], LiveCursor]:
    """Everything the stream should say next, and where the cursors land.

    Pure with respect to time and I/O-free beyond the queries it's given, so
    the streaming loop in `solar_live_events` stays a thin wrapper and the
    logic here is testable without sleeping or opening a socket.
    """
    freshness = live_freshness(session, facility_id, now)
    payloads: list[tuple[str, BaseModel]] = []

    if initial:
        payloads.append(
            (
                "snapshot",
                SolarLiveSnapshot(
                    facility_id=facility_id,
                    # `now.date()`, not `period_end`: period_end is the
                    # ledger's window (the last billing month on file) and a
                    # live reading routinely postdates it — capping the
                    # summary to period_end would make "latest" silently
                    # ignore every reading the stream is about to deliver.
                    health=solar_health_summary(session, facility_id, now.date()),
                    series=generation_vs_consumption_series(
                        session, facility_id, period_start, period_end
                    ),
                    freshness=freshness,
                ),
            )
        )
        # Baseline, don't replay: the page loaded this history over REST
        # already, and both of those series are in the snapshot above.
        # Establishing the cursors here is what keeps the first connected
        # poll from re-sending months of daily readings, and it lets the rest
        # of this function run unchanged — with nothing new to report, it
        # falls straight through to the heartbeat.
        cursor = LiveCursor(
            health_ts=session.scalar(
                select(func.max(SolarHealthReading.ts)).where(
                    SolarHealthReading.facility_id == facility_id
                )
            ),
            generation_marker=_generation_marker(session, facility_id, period_start, period_end),
        )

    health_filters = [SolarHealthReading.facility_id == facility_id]
    if cursor.health_ts is not None:
        health_filters.append(SolarHealthReading.ts > cursor.health_ts)
    new_readings = session.scalars(
        select(SolarHealthReading)
        .where(*health_filters)
        .order_by(SolarHealthReading.ts.asc())
    ).all()

    if new_readings:
        payloads.append(
            (
                "health",
                SolarLiveHealthUpdate(
                    points=[
                        SolarHealthPoint(
                            # Full timestamp — see SolarHealthPoint's comment.
                            ts=r.ts,
                            battery_soc_pct=float(r.battery_soc_pct)
                            if r.battery_soc_pct is not None
                            else None,
                            battery_soh_pct=float(r.battery_soh_pct)
                            if r.battery_soh_pct is not None
                            else None,
                        )
                        for r in new_readings
                    ],
                    health=solar_health_summary(session, facility_id, now.date()),
                    freshness=freshness,
                ),
            )
        )
        cursor = replace(cursor, health_ts=new_readings[-1].ts)

    marker = _generation_marker(session, facility_id, period_start, period_end)
    if marker != cursor.generation_marker:
        payloads.append(
            (
                "series",
                SolarLiveSeriesUpdate(
                    series=generation_vs_consumption_series(
                        session, facility_id, period_start, period_end
                    ),
                    freshness=freshness,
                ),
            )
        )
        cursor = replace(cursor, generation_marker=marker)

    payloads.append(("tick", SolarLiveTick(freshness=freshness)))
    return payloads, cursor


def format_event(event: str, payload: BaseModel) -> str:
    """One SSE frame. `model_dump_json` (not `json.dumps`) so Decimal and
    date columns serialize the same way every other endpoint's
    `model_dump(mode="json")` serializes them."""
    return f"event: {event}\ndata: {payload.model_dump_json()}\n\n"


def make_poll(engine: Engine, org_id: str, facility_id: UUID) -> Callable[..., tuple]:
    """One poll: its own session, its own tenant context, its own
    transaction — so each poll releases its pooled connection before the
    generator parks on a sleep. Holding one open between polls would exhaust
    the pool with a handful of idle browser tabs."""

    def poll(cursor: LiveCursor, **kwargs) -> tuple[list[tuple[str, BaseModel]], LiveCursor]:
        with Session(engine) as session:
            try:
                _set_tenant(session, org_id)
                return next_live_payloads(session, facility_id, cursor, **kwargs)
            finally:
                session.rollback()

    return poll


def solar_live_events(
    engine: Engine,
    org_id: str,
    facility_id: UUID,
    *,
    interval_s: float = DEFAULT_INTERVAL_S,
    period_start: date | None = None,
    period_end: date | None = None,
    max_ticks: int | None = None,
    sleep: Callable[[float], None] = time.sleep,
    now_fn: Callable[[], datetime] | None = None,
    poll_fn: Callable[..., tuple] | None = None,
) -> Iterator[str]:
    """Yield SSE frames until the client disconnects (or `max_ticks` is hit).

    `sleep`/`now_fn`/`max_ticks`/`poll_fn` are seams for tests — production
    callers pass nothing and get real time and a real database. Splitting the
    poll out here keeps the loop's own contract (frame format, cadence,
    termination, and never suspending inside an open transaction) testable
    without a socket or a clock.
    """
    period_end = period_end or date.today()
    period_start = period_start or _months_before(period_end, DEFAULT_LOOKBACK_MONTHS)
    now_fn = now_fn or (lambda: datetime.now(timezone.utc))

    poll = poll_fn or make_poll(engine, org_id, facility_id)
    cursor = LiveCursor()
    initial = True
    ticks = 0
    while max_ticks is None or ticks < max_ticks:
        payloads, cursor = poll(
            cursor,
            period_start=period_start,
            period_end=period_end,
            now=now_fn(),
            initial=initial,
        )
        initial = False
        # Yielding only after `poll` has closed its session keeps the
        # generator's suspension points outside any open transaction.
        for event, payload in payloads:
            yield format_event(event, payload)

        ticks += 1
        if max_ticks is not None and ticks >= max_ticks:
            break
        sleep(interval_s)
