import uuid

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class SolarIrradianceDaily(Base):
    """Cached daily solar irradiance per facility — see migrations/0003 for
    why this is a cache table rather than a live lookup."""

    __tablename__ = "solar_irradiance_daily"
    __table_args__ = (UniqueConstraint("facility_id", "day"),)

    facility_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("facility.id"), nullable=False, index=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id"), nullable=False
    )
    day: Mapped[object] = mapped_column(Date, nullable=False)
    ghi_kwh_per_m2: Mapped[float] = mapped_column(Numeric, nullable=False)
    source: Mapped[str] = mapped_column(nullable=False)
    fetched_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
