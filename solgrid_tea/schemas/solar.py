from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

PanelStatus = Literal["normal", "underperforming", "fault"]
BatteryStatus = Literal["normal", "degraded", "fault"]
InsightSeverity = Literal["info", "warn", "critical"]


class SolarQuery(BaseModel):
    facility_id: UUID
    period_start: date
    period_end: date

    @model_validator(mode="after")
    def _check_period_order(self):
        if self.period_end < self.period_start:
            raise ValueError("period_end must be on or after period_start")
        return self


class SolarHealthQuery(BaseModel):
    facility_id: UUID
    as_of: date | None = None


class GenerationVsConsumptionPoint(BaseModel):
    period_start: date
    period_end: date
    generation_kwh: float
    consumption_kwh: float  # grid + diesel(kWh-equiv) + solar_generation — total electrical load
    self_consumption_pct: float | None  # share of consumption covered by solar, None if consumption is 0
    # Weather-adjusted expected generation for this period — install_capacity_kw
    # x cached daily irradiance x a standard performance ratio (see
    # solar_insights.py). None when there's no install capacity on file or
    # irradiance coverage for the period is too incomplete to trust — never
    # a guess standing in for missing data.
    expected_generation_kwh: float | None = None


class GenerationVsConsumptionSeries(BaseModel):
    facility_id: UUID
    install_capacity_kw: float | None
    points: list[GenerationVsConsumptionPoint]


class SolarHealthLatest(BaseModel):
    # A timestamp, not a date: this is now the newest point on a chart that a
    # live feed appends to, so two readings on the same day have to be
    # distinguishable. Truncating to a date collapsed every intra-day reading
    # onto the same x position.
    ts: datetime
    battery_soc_pct: float | None
    battery_soh_pct: float | None
    panel_status: PanelStatus
    battery_status: BatteryStatus
    panel_temp_c: float | None
    note: str | None


class SolarInsight(BaseModel):
    severity: InsightSeverity
    message: str


class SolarHealthSummary(BaseModel):
    facility_id: UUID
    latest: SolarHealthLatest | None
    battery_soh_trend_pct: float | None  # change over the trailing window, negative = degrading
    insights: list[SolarInsight]


class SolarHealthPoint(BaseModel):
    ts: datetime
    battery_soc_pct: float | None
    battery_soh_pct: float | None


# ---------- realtime feed (GET /api/v1/solar/live) ----------


class SolarLiveQuery(BaseModel):
    facility_id: UUID
    # Both optional, and both worth passing: the page sends the same window
    # it used for its REST loads, so a live `series` event replaces the
    # chart's points with an identically-windowed series instead of one that
    # suddenly spans a different number of months.
    period_start: date | None = None
    period_end: date | None = None
    # Bounded so a client can't ask to be polled hard enough to matter —
    # this is a dashboard, not a telemetry firehose.
    interval_s: float | None = Field(default=None, ge=1, le=30)

    @model_validator(mode="after")
    def _check_period_order(self):
        if self.period_start and self.period_end and self.period_end < self.period_start:
            raise ValueError("period_end must be on or after period_start")
        return self


class SolarLiveFreshness(BaseModel):
    """How current the newest reading actually is. Sent on every event,
    including polls where nothing new arrived — a live view that can't tell
    "quiet" from "dead" is worse than no live view. See solar_live.py."""

    server_ts: datetime
    latest_health_ts: datetime | None
    latest_health_age_s: float | None  # seconds since that reading, None if there are none
    is_stale: bool


class SolarLiveSnapshot(BaseModel):
    """Sent once when a stream connects, so a viewer is never looking at an
    empty panel while waiting for the next reading. Carries the health
    *summary* and the generation series but deliberately not the raw health
    history — the page already loaded that over REST, and re-sending months
    of daily points on every reconnect is a lot of bytes for a curve the
    chart already has."""

    facility_id: UUID
    health: SolarHealthSummary
    series: GenerationVsConsumptionSeries
    freshness: SolarLiveFreshness


class SolarLiveHealthUpdate(BaseModel):
    """New solar_health_reading rows since the last poll, oldest first, plus
    the summary recomputed to include them."""

    points: list[SolarHealthPoint]
    health: SolarHealthSummary
    freshness: SolarLiveFreshness


class SolarLiveSeriesUpdate(BaseModel):
    """The generation-vs-consumption series, re-sent only when the rows
    behind it changed."""

    series: GenerationVsConsumptionSeries
    freshness: SolarLiveFreshness


class SolarLiveTick(BaseModel):
    """Heartbeat: no new data, just proof the stream is alive and a fresh
    reading age."""

    freshness: SolarLiveFreshness
