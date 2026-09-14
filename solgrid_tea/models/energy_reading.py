import uuid

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Numeric, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from solgrid_tea.extensions import db

READING_TYPES = ("grid_electricity", "diesel", "fuelwood", "solar_generation")
SOURCE_CHANNELS = ("esp32", "modbus", "oem_api", "manual", "sms")


class EnergyReading(db.Model):
    """The ledger. One typed row per energy input for a matched period.

    Primary key is (id, period_start) rather than plain id: TimescaleDB
    requires any unique/primary key constraint on a hypertable to include
    the partitioning column.
    """

    __tablename__ = "energy_reading"
    __table_args__ = (
        CheckConstraint(
            "reading_type IN ('grid_electricity','diesel','fuelwood','solar_generation')",
            name="ck_energy_reading_type",
        ),
        CheckConstraint(
            "source_channel IN ('esp32','modbus','oem_api','manual','sms')",
            name="ck_energy_reading_source_channel",
        ),
        CheckConstraint("quantity > 0", name="ck_energy_reading_quantity_positive"),
        CheckConstraint("period_end >= period_start", name="ck_energy_reading_period_order"),
        CheckConstraint(
            "cost_kes IS NULL OR cost_kes >= 0", name="ck_energy_reading_cost_nonnegative"
        ),
        CheckConstraint(
            "moisture_pct IS NULL OR (moisture_pct >= 0 AND moisture_pct <= 100)",
            name="ck_energy_reading_moisture_range",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    period_start: Mapped[object] = mapped_column(Date, primary_key=True, nullable=False)

    facility_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("facility.id"), nullable=False, index=True
    )
    # Denormalized from facility_id by a DB trigger (never client-supplied) so
    # every tenant-scoped table has a direct organization_id column and RLS
    # policies can be flat equality checks instead of subqueries via facility.
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id"), nullable=False
    )

    reading_type: Mapped[str] = mapped_column(nullable=False)
    period_end: Mapped[object] = mapped_column(Date, nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric, nullable=False)
    unit: Mapped[str] = mapped_column(nullable=False)
    cost_kes: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    moisture_pct: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    source_plantation: Mapped[str | None] = mapped_column(nullable=True)
    source_channel: Mapped[str] = mapped_column(nullable=False)

    entered_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id"), nullable=True
    )
    entered_by_phone: Mapped[str | None] = mapped_column(nullable=True)

    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
