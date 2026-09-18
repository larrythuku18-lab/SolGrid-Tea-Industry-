import uuid

from sqlalchemy import ForeignKey, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class Facility(Base, TimestampMixin):
    __tablename__ = "facility"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(nullable=False)
    county: Mapped[str | None] = mapped_column(nullable=True)
    install_capacity_kw: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    # Approximate, per facility — see migrations/0003. Needed to look up
    # real solar irradiance for weather-adjusted generation checks; not a
    # verified GPS survey of either site.
    latitude: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    is_active: Mapped[bool] = mapped_column(nullable=False, server_default="true")

    organization: Mapped["Organization"] = relationship(back_populates="facilities")
