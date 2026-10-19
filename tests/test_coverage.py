import json
import shutil
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.coverage import EF, VF, coverage
from core.models import Variant
from core.storage import Store
from pipeline.importers import eea
from service.app import create_app
from service.mcp_server import build_mcp
from tests.test_mcp import call

ROWS = json.loads((Path(__file__).parent / "fixtures" / "eea_sample.json").read_text(encoding="utf-8"))["results"]
B = "/api/v1"


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    p = tmp_path_factory.mktemp("cov") / "v.db"
    with Store(p) as st:
        eea.load(ROWS, st, 2025, date(2026, 9, 19))
        vs = st.find(Variant, sort="-registrations")
        st.put(vs[0].model_copy(update={"type_approval": "e3*2007/46*0064"}))
    return p, vs[0]


def test_overall_counts_and_shares(db):
    with Store(db[0], ro=True) as st:
        c = coverage(st)
    o = c.overall
    assert o.variants == 14 and o.registrations == sum(b.registrations for b in c.brands)
    f = o.fields["type_approval"]
    assert f.variants == 1 and f.share == round(1 / 14, 4)
    assert f.weighted == round(db[1].registrations / o.registrations, 4)
    assert o.fields["mass_kg"].variants == 14 and o.fields["mass_kg"].share == 1.0
    assert set(o.fields) == {*VF, *EF}


def test_brands_add_up_to_the_overall(db):
    with Store(db[0], ro=True) as st:
        c = coverage(st)
    assert sum(b.variants for b in c.brands) == c.overall.variants
    assert all(b.name for b in c.brands) and [b.brand_id for b in c.brands] == sorted(b.brand_id for b in c.brands)
    for f in c.overall.fields:
        assert sum(b.fields[f].variants for b in c.brands) == c.overall.fields[f].variants


def test_one_brand(db):
    with Store(db[0], ro=True) as st:
        c = coverage(st, "brand_fiat")
    assert [b.brand_id for b in c.brands] == ["brand_fiat"] and c.overall.variants == c.brands[0].variants


def test_an_empty_dataset_has_no_fields():
    with Store() as st:
        c = coverage(st)
    assert c.brands == [] and c.overall.variants == 0 and c.overall.fields == {}


def test_weighted_is_none_without_registrations():
    with Store() as st:
        eea.load([{"Mk": "X", "Cn": "Y", "T": "1", "Va": "a", "Ve": "b", "Ft": "petrol", "Fm": "M", "ec": 1, "ep": 1, "m": 1000, "w": None, "at1": None, "co2": 1, "n": 0}], st, 2025, date(2026, 9, 19))
        assert coverage(st).overall.fields["mass_kg"].weighted is None


def test_store_rejects_unknown_columns():
    with Store() as st:
        with pytest.raises(ValueError):
            st.coverage(("nope",), ())
        with pytest.raises(ValueError):
            st.coverage((), ("nope",))


def test_meta_carries_the_overall_coverage(db):
    c = TestClient(create_app(db[0]))
    j = c.get(f"{B}/meta").json()["coverage"]
    assert j["variants"] == 14 and j["fields"]["type_approval"]["variants"] == 1


def test_coverage_endpoint(db):
    c = TestClient(create_app(db[0]))
    j = c.get(f"{B}/coverage").json()
    assert j["overall"]["variants"] == 14 and len(j["brands"]) == 6
    one = c.get(f"{B}/coverage", params={"brand_id": "brand_fiat"}).json()
    assert [b["brand_id"] for b in one["brands"]] == ["brand_fiat"]
    r = c.get(f"{B}/coverage", params={"brand_id": "brand_fiatt"})
    assert r.status_code == 404 and "brand_fiat" in r.json()["detail"]


def test_mcp_dataset_info_has_the_coverage(db):
    assert call(build_mcp(db[0]), "dataset_info")["coverage"]["variants"] == 14
