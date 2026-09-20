import argparse
import json
from datetime import date
from pathlib import Path

from pydantic import Field, model_validator

from core.models import Base, Brand
from core.provenance import Evidence, FieldProvenance
from core.storage import Store
from pipeline.importers.corrections import norm
from pipeline.sources import WIKIDATA

PATH = Path(__file__).with_name("wikidata.json")
URL = "https://www.wikidata.org/wiki/"


class Entry(Base):
    id: str = Field(pattern=r"^Q[1-9]\d*$")
    label: str = Field(min_length=1)
    reason: str = Field(min_length=10)


class WikidataMap(Base):
    brands: dict[str, Entry] = {}

    @model_validator(mode="after")
    def _check(self):
        ks = [norm(k) for k in self.brands]
        if not all(ks):
            raise ValueError("empty brand name")
        if len(set(ks)) != len(ks):
            raise ValueError("duplicate brand")
        ids = [e.id for e in self.brands.values()]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate id")
        return self


def load_wikidata(path=PATH):
    return WikidataMap.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))


def apply(st, wm, today=None):
    today = today or date.today()
    idx = {norm(k): (k, e) for k, e in wm.brands.items()}
    bs, pv, used = [], [], set()
    for b in st.find(Brand):
        k, e = idx.get(norm(b.name), (None, None))
        if e is None:
            continue
        used.add(k)
        bs.append(b.model_copy(update={"wikidata_id": e.id}))
        pv.append(FieldProvenance(entity_id=b.id, field="wikidata_id", evidence=[Evidence(source_id=WIKIDATA.id, value=e.id, url=URL + e.id, retrieved=today)], last_verified=today))
    st.put(WIKIDATA, *bs)
    st.put_prov(*pv)
    return {"brands": len(bs), "unused": sorted(set(wm.brands) - used)}


def run(db, path=PATH, today=None):
    with Store(db) as st:
        return apply(st, load_wikidata(path), today)


def main(argv=None):
    a = argparse.ArgumentParser(prog="python -m pipeline.importers.wikidata")
    a.add_argument("--db", required=True)
    print(run(a.parse_args(argv).db))


if __name__ == "__main__":
    main()
