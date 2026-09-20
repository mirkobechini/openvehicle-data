import json
from datetime import date

import pytest
from pydantic import ValidationError

from core.models import Brand
from core.provenance import Status
from core.storage import Store
from pipeline.importers import wikidata as wd
from pipeline.sources import WIKIDATA
from pipeline.validation import validate

TODAY = date(2026, 9, 20)
R = "reviewed from its label and description"


def entry(i="Q27597", label="Fiat"):
    return {"id": i, "label": label, "reason": R}


def wmap(**brands):
    return wd.WikidataMap.model_validate({"brands": brands})


@pytest.fixture
def st():
    with Store() as s:
        s.put(Brand(id="brand_fiat", name="FIAT"), Brand(id="brand_ford", name="FORD"), Brand(id="brand_mercedes-amg", name="MERCEDES AMG"), Brand(id="brand_dr", name="DR"))
        yield s


def test_shipped_mapping_is_valid():
    m = wd.load_wikidata()
    assert len(m.brands) >= 70
    assert m.brands["FIAT"].id == "Q27597" and m.brands["VOLKSWAGEN"].id == "Q246" and m.brands["TOYOTA"].id == "Q53268"
    assert all(len(e.reason) >= 10 and e.label for e in m.brands.values())
    assert not {"EMC", "SMART", "MOKE", "SHINERAY", "RENAULT", "SSANGYONG", "SERES", "DFSK"} & set(m.brands)


def test_shipped_mapping_is_next_to_the_module():
    assert wd.PATH.name == "wikidata.json" and wd.PATH.is_file()


def test_load_from_a_custom_path(tmp_path):
    f = tmp_path / "w.json"
    f.write_text(json.dumps({"brands": {"FIAT": entry()}}), encoding="utf-8")
    assert wd.load_wikidata(f).brands["FIAT"].id == "Q27597"


def test_empty_mapping_is_valid():
    assert wd.WikidataMap.model_validate({}).brands == {}


@pytest.mark.parametrize("bad", [
    {"FIAT": {**entry(), "id": "27597"}}, {"FIAT": {**entry(), "id": "Q0"}}, {"FIAT": {**entry(), "reason": "short"}},
    {"FIAT": {**entry(), "label": ""}}, {"FIAT": {**entry(), "extra": 1}}, {"": entry()}, {"!!!": entry()},
    {"FIAT": entry(), "fiat": entry("Q2")}, {"FIAT": entry(), "FORD": entry()},
])
def test_invalid_mapping(bad):
    with pytest.raises(ValidationError):
        wmap(**bad)


def test_apply_sets_the_id_and_the_source(st):
    r = wd.apply(st, wmap(FIAT=entry(), **{"MERCEDES AMG": entry("Q26966", "Mercedes-AMG")}), TODAY)
    assert r == {"brands": 2, "unused": []}
    assert st.get(Brand, "brand_fiat").wikidata_id == "Q27597" and st.get(Brand, "brand_mercedes-amg").wikidata_id == "Q26966"
    assert st.get(Brand, "brand_ford").wikidata_id is None
    p = st.prov("brand_fiat")[0]
    assert (p.field, p.status) == ("wikidata_id", Status.SINGLE) and p.last_verified == TODAY
    assert [(e.source_id, e.value, e.url, e.retrieved) for e in p.evidence] == [("wikidata", "Q27597", "https://www.wikidata.org/wiki/Q27597", TODAY)]
    assert st.get(type(WIKIDATA), "wikidata") == WIKIDATA
    assert validate(st) == []


def test_apply_matches_names_loosely(st):
    r = wd.apply(st, wmap(**{"mercedes-amg": entry("Q26966", "Mercedes-AMG")}), TODAY)
    assert r["brands"] == 1 and st.get(Brand, "brand_mercedes-amg").wikidata_id == "Q26966"


def test_apply_reports_entries_without_a_brand(st):
    r = wd.apply(st, wmap(FIAT=entry(), OPEL=entry("Q40966", "Opel"), AUDI=entry("Q23317", "Audi AG")), TODAY)
    assert r == {"brands": 1, "unused": ["AUDI", "OPEL"]}


def test_apply_keeps_the_other_brand_fields(st):
    st.put(Brand(id="brand_fiat", name="FIAT", aliases=["Fiat Auto"]))
    wd.apply(st, wmap(FIAT=entry()), TODAY)
    b = st.get(Brand, "brand_fiat")
    assert (b.name, b.aliases, b.wikidata_id) == ("FIAT", ["Fiat Auto"], "Q27597")


def test_apply_twice_gives_the_same_result(st):
    a = wd.apply(st, wmap(FIAT=entry()), TODAY)
    assert wd.apply(st, wmap(FIAT=entry()), TODAY) == a and len(st.prov("brand_fiat")) == 1


def test_run(tmp_path):
    db = tmp_path / "r.db"
    with Store(db) as s:
        s.put(Brand(id="brand_fiat", name="FIAT"))
    f = tmp_path / "w.json"
    f.write_text(json.dumps({"brands": {"FIAT": entry()}}), encoding="utf-8")
    assert wd.run(db, f, TODAY) == {"brands": 1, "unused": []}
    with Store(db, ro=True) as s:
        assert s.get(Brand, "brand_fiat").wikidata_id == "Q27597"


def test_main(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(wd, "run", lambda *a: calls.append(a) or {"ok": 1})
    wd.main(["--db", "x.db"])
    assert calls == [("x.db",)] and "'ok': 1" in capsys.readouterr().out


@pytest.mark.parametrize("brand,q", [
    ("SUZUKI", "Q181642"), ("BENTLEY", "Q27224"), ("DS", "Q16040593"), ("MG", "Q1881443"), ("LYNK&CO", "Q27555283"),
    ("GENESIS", "Q21451523"), ("LOTUS", "Q35935"), ("CHERY", "Q98172997"), ("BYD", "Q27423"),
])
def test_shipped_ids_of_the_second_group_of_brands(brand, q):
    assert wd.load_wikidata().brands[brand].id == q


def test_shipped_ids_are_unique_and_labelled():
    b = wd.load_wikidata().brands
    assert len({e.id for e in b.values()}) == len(b) and all(e.label for e in b.values())
