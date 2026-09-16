import uuid

from sqlalchemy import DateTime, ForeignKey, Numeric, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class SolarHealthReading(Base):
    """Panel/battery telemetry — separate from energy_reading because this
    is device diagnostic state (SoC, SoH, fault status), not a ledger entry
    with a cost and a matched period. See migrations/0002 for why this
    exists ahead of real hardware."""

    __tablename__ = "solar_health_reading"

    facility_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("facility.id"), nullable=False, index=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id"), nullable=False
    )
    ts: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    battery_soc_pct: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    battery_soh_pct: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    panel_status: Mapped[str] = mapped_column(nullable=False)
    battery_status: Mapped[str] = mapped_column(nullable=False)
    panel_temp_c: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    note: Mapped[str | None] = mapped_column(nullable=True)
    source_channel: Mapped[str] = mapped_column(nullable=False)
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
