from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from solgrid_tea.models import EmissionFactor


def latest_emission_factor(session: Session, fuel_type: str, as_of: date) -> EmissionFactor | None:
    return session.scalars(
        select(EmissionFactor)
        .where(EmissionFactor.fuel_type == fuel_type, EmissionFactor.effective_from <= as_of)
        .order_by(EmissionFactor.effective_from.desc())
        .limit(1)
    ).first()
