import re
from typing import Literal

from pydantic import Field, model_validator

from core.models import Base

COMBINED = "co2cars"
RECORDS = "https://sdi.eea.europa.eu/catalogue/srv/eng/catalog.search#/metadata/"


class Dataset(Base):
    year: int = Field(ge=2010, le=2100)
    table: str = Field(pattern=r"^[A-Za-z0-9_]+$")
    status: Literal["F", "P"]
    record: str = Field(pattern=r"^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$")

    @model_validator(mode="after")
    def _check(self):
        if self.table != COMBINED and str(self.year) not in self.table:
            raise ValueError(f"table {self.table} does not look like year {self.year}")
        return self

    @property
    def url(self):
        return RECORDS + self.record


def _d(year, table, status, record):
    return Dataset(year=year, table=table, status=status, record=record)


DATASETS = {
    d.year: d
    for d in (
        _d(2019, COMBINED, "F", "a0da862c-0bed-460f-808a-0bae489b12b9"),
        _d(2020, "co2cars_2020Fv22", "F", "47a7277f-d111-47ba-8438-d669b1057b6d"),
        _d(2021, "co2cars_2021Fv24", "F", "0172c621-9e03-4756-ac5f-47cc3e241201"),
        _d(2022, "co2cars_2022Fv26", "F", "992616f8-158f-4ecc-b978-814b81629db6"),
        _d(2023, "co2cars_2023Fv28", "F", "87fd2bce-6ad5-46d8-af41-f27cfd2e45a8"),
        _d(2024, "co2cars_2024Fv30", "F", "5018ec17-2348-4c92-8761-6f2377bbd1c0"),
        _d(2025, "co2cars_2025Pv31", "P", "b4044b06-2e6b-4f8e-a6e6-66e0e98bb0dd"),
    )
}


def parse_years(s):
    ys = set()
    s = ",".join(map(str, s)) if isinstance(s, (list, tuple, set)) else s
    for p in str(s).replace(" ", "").split(","):
        m = re.fullmatch(r"(\d{4})(?:-(\d{4}))?", p)
        if not m:
            raise ValueError(f"bad years {s!r}: use 2025, 2019-2025 or 2021,2023")
        a, b = int(m[1]), int(m[2] or m[1])
        if b < a:
            raise ValueError(f"bad range {p!r}")
        ys |= set(range(a, b + 1))
    bad = sorted(ys - set(DATASETS))
    if bad:
        raise ValueError(f"no dataset for {bad}; available: {min(DATASETS)}-{max(DATASETS)}")
    return sorted(ys)
