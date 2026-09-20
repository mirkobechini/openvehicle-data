from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from core.enums import Category, Fuel

BrandId = Annotated[str, Field(pattern=r"^brand_[a-z0-9]+(-[a-z0-9]+)*$")]
ModelId = Annotated[str, Field(pattern=r"^model_[a-z0-9]+(-[a-z0-9]+)*$")]
FamId = Annotated[str, Field(pattern=r"^family_[a-z0-9]+(-[a-z0-9]+)*$")]
GenId = Annotated[str, Field(pattern=r"^gen_[a-z0-9]+(-[a-z0-9]+)*$")]
EngId = Annotated[str, Field(pattern=r"^eng_[a-z0-9]+(-[a-z0-9]+)*$")]
VarId = Annotated[str, Field(pattern=r"^var_[a-z0-9]+(-[a-z0-9]+)*$")]
Year = Annotated[int, Field(ge=1886, le=2100)]


class Base(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Named(Base):
    name: str = Field(min_length=1)
    aliases: list[str] = []

    @field_validator("aliases")
    @classmethod
    def _al(cls, v):
        return list(dict.fromkeys(a.strip() for a in v if a.strip()))


class Period(Base):
    year_from: Year
    year_to: Year | None = None

    @model_validator(mode="after")
    def _yr(self):
        if self.year_to is not None and self.year_to < self.year_from:
            raise ValueError("year_to before year_from")
        return self


class Brand(Named):
    id: BrandId


class Family(Named):
    id: FamId
    brand_id: BrandId
    model_count: int = Field(ge=1)
    registrations: int | None = Field(default=None, ge=0)


class CarModel(Named):
    id: ModelId
    brand_id: BrandId
    category: Category = Category.M1
    registrations: int | None = Field(default=None, ge=0)
    family_id: FamId | None = None


class Generation(Named, Period):
    id: GenId
    model_id: ModelId


class Engine(Base):
    id: EngId
    fuel: Fuel
    displacement_cc: int | None = Field(default=None, ge=0, le=10000)
    power_kw: float | None = Field(default=None, gt=0, le=2000)


class Variant(Named, Period):
    id: VarId
    generation_id: GenId
    engine_id: EngId
    mass_kg: float | None = Field(default=None, gt=0, le=10000)
    wheelbase_mm: int | None = Field(default=None, ge=500, le=5000)
    track_width_mm: int | None = Field(default=None, ge=500, le=3000)
    co2_wltp_g_km: float | None = Field(default=None, ge=0, le=1000)
    registrations: int | None = Field(default=None, ge=0)
    type_approval: str | None = Field(default=None, pattern=r"^e\d{1,3}\*[^*\s]+\*[^*\s]+$")
