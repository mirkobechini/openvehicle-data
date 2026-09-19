import json
from pathlib import Path

from pydantic import Field, model_validator

from core.ids import slug
from core.models import Base

PATH = Path(__file__).with_name("corrections.json")


def norm(s):
    return slug(s).replace("-", "")


class Exclusion(Base):
    brand: str = Field(min_length=1)
    model: str = Field(min_length=1)
    reason: str = Field(min_length=10)


class Corrections(Base):
    brands: dict[str, str] = {}
    exclude_models: list[Exclusion] = []

    @model_validator(mode="after")
    def _check(self):
        keys = {norm(k) for k in self.brands}
        if len(keys) != len(self.brands):
            raise ValueError("duplicate brand spelling")
        for k, v in self.brands.items():
            if not norm(k) or not norm(v):
                raise ValueError(f"empty brand name in {k!r}")
            if norm(k) == norm(v):
                raise ValueError(f"{k!r} maps to itself")
            if norm(v) in keys:
                raise ValueError(f"{k!r} maps to {v!r}, which is itself corrected")
        pairs = [(norm(x.brand), slug(x.model)) for x in self.exclude_models]
        if len(set(pairs)) != len(pairs):
            raise ValueError("duplicate exclusion")
        return self


def load_corrections(path=PATH):
    return Corrections.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))
