import json
import re
from pathlib import Path

from pydantic import Field, model_validator

from core.models import Base
from pipeline.importers.corrections import norm

PATH = Path(__file__).with_name("families.json")


class Rule(Base):
    pattern: str = Field(min_length=1)
    family: str = Field(min_length=1)

    @model_validator(mode="after")
    def _check(self):
        try:
            rx = re.compile(self.pattern, re.IGNORECASE)
        except re.error as e:
            raise ValueError(f"bad pattern {self.pattern!r}: {e}") from None
        if any(int(g) > rx.groups for g in re.findall(r"\\(\d+)", self.family)):
            raise ValueError(f"{self.family!r} uses a group that {self.pattern!r} does not have")
        return self


class BrandRules(Base):
    reason: str = Field(min_length=10)
    rules: list[Rule] = Field(min_length=1)


class FamilyRules(Base):
    brands: dict[str, BrandRules] = {}

    @model_validator(mode="after")
    def _check(self):
        keys = [norm(k) for k in self.brands]
        if not all(keys):
            raise ValueError("empty brand name")
        if len(set(keys)) != len(keys):
            raise ValueError("duplicate brand")
        return self


def load_family_rules(path=PATH):
    return FamilyRules.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))


def family_of(fr, brand, name):
    idx = {norm(k): v for k, v in fr.brands.items()}
    for r in idx[norm(brand)].rules if norm(brand) in idx else ():
        m = re.search(r.pattern, name, re.IGNORECASE)
        f = " ".join(m.expand(r.family).upper().split()) if m else ""
        if f:
            return f
    return name
