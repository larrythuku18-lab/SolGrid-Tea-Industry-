from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class Organization(Base, TimestampMixin):
    __tablename__ = "organization"

    name: Mapped[str] = mapped_column(nullable=False)
    sector: Mapped[str] = mapped_column(nullable=False, server_default="tea")

    facilities: Mapped[list["Facility"]] = relationship(back_populates="organization")
    users: Mapped[list["AppUser"]] = relationship(back_populates="organization")
