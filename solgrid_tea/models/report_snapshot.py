import uuid

from sqlalchemy import Date, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ReportSnapshot(Base):
    __tablename__ = "report_snapshot"

    facility_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("facility.id"), nullable=False, index=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id"), nullable=False
    )
    period_start: Mapped[object] = mapped_column(Date, nullable=False)
    period_end: Mapped[object] = mapped_column(Date, nullable=False)
    published_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    methodology_version: Mapped[str] = mapped_column(nullable=False)
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("report_snapshot.id"), nullable=True
    )
