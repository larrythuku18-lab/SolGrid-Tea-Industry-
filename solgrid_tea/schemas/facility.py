from uuid import UUID

from pydantic import BaseModel, Field


class FacilityCreate(BaseModel):
    name: str = Field(min_length=1)
    county: str | None = None
    install_capacity_kw: float | None = Field(default=None, gt=0)


class FacilityOut(BaseModel):
    id: UUID
    name: str
    county: str | None
    install_capacity_kw: float | None
    is_active: bool
