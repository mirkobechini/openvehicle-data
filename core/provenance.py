from datetime import date
from enum import StrEnum
from typing import Annotated

from pydantic import Field, computed_field, model_validator

from core.models import Base

Url = Annotated[str, Field(pattern=r"^https?://\S+$")]
SrcId = Annotated[str, Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")]


class Status(StrEnum):
    SINGLE = "single_source"
    CONFIRMED = "confirmed"
    CONFLICT = "conflict"


class Source(Base):
    id: SrcId
    name: str = Field(min_length=1)
    license: str = Field(min_length=1)
    license_url: Url
    license_checked: date | None = None

    @property
    def usable(self):
        return self.license_checked is not None


class Evidence(Base):
    source_id: SrcId
    value: str | int | float | None
    url: Url | None = None
    retrieved: date


class FieldProvenance(Base):
    entity_id: str = Field(min_length=1)
    field: str = Field(min_length=1)
    evidence: list[Evidence] = Field(min_length=1)
    last_verified: date

    @model_validator(mode="before")
    @classmethod
    def _derived(cls, d):
        return {k: v for k, v in d.items() if k != "status"} if isinstance(d, dict) else d

    @computed_field
    @property
    def status(self) -> Status:
        if len({e.value for e in self.evidence}) > 1:
            return Status.CONFLICT
        if len({e.source_id for e in self.evidence}) > 1:
            return Status.CONFIRMED
        return Status.SINGLE
