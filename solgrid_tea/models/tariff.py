import uuid

from sqlalchemy import Date, ForeignKey, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class Tariff(Base, TimestampMixin):
    __tablename__ = "tariff"

    # organization_id is required (unlike the doc's version) so an org-default
    # row (facility_id NULL) is still tenant-scoped by RLS. Without it, a NULL
    # facility_id would make the row visible to every tenant, not just its own.
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id"), nullable=False, index=True
    )
    facility_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("facility.id"), nullable=True
    )
    fuel_type: Mapped[str] = mapped_column(nullable=False)
    price_kes_per_unit: Mapped[float] = mapped_column(Numeric, nullable=False)
    effective_from: Mapped[object] = mapped_column(Date, nullable=False)
