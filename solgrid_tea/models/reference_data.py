from sqlalchemy import Date, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class EmissionFactor(Base, TimestampMixin):
    """Versioned, sourced. Never hardcode a gCO2/unit constant in Python —
    add a row here with a methodology_note instead."""

    __tablename__ = "emission_factor"

    fuel_type: Mapped[str] = mapped_column(nullable=False, index=True)
    kg_co2_per_unit: Mapped[float] = mapped_column(Numeric, nullable=False)
    unit: Mapped[str] = mapped_column(nullable=False)
    effective_from: Mapped[object] = mapped_column(Date, nullable=False)
    methodology_note: Mapped[str] = mapped_column(nullable=False)


class EnergyContentFactor(Base, TimestampMixin):
    """Calorific-value reference table. Not in the original architecture
    doc — added because cost/kg, MJ/kg, and energy-mix % all require
    converting litres of diesel and m3 of fuelwood into a common energy
    unit (kWh), and that conversion is exactly the kind of number principle
    §0.2 says must be traceable to a source, not a constant buried in a
    formula."""

    __tablename__ = "energy_content_factor"

    fuel_type: Mapped[str] = mapped_column(nullable=False, index=True)
    kwh_per_unit: Mapped[float] = mapped_column(Numeric, nullable=False)
    unit: Mapped[str] = mapped_column(nullable=False)
    effective_from: Mapped[object] = mapped_column(Date, nullable=False)
    methodology_note: Mapped[str] = mapped_column(nullable=False)
