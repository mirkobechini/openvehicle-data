import sqlite3
from datetime import date

import pytest

from core.enums import Fuel
from core.models import Brand, CarModel, Engine, Generation, Variant
from core.provenance import Evidence, FieldProvenance, Source, Status
from core.storage import Store

D = date(2026, 9, 19)
B = Brand(id="brand_citroen", name="Citroën", aliases=["Citroen", "Citroën SA"])
M = CarModel(id="model_citroen-c3", brand_id="brand_citroen", name="C3")
G = Generation(id="gen_citroen-c3-2016", model_id="model_citroen-c3", name="III", year_from=2016)
E = Engine(id="eng_petrol-1199-60", fuel=Fuel.PETROL, displacement_cc=1199, power_kw=60)
V = Variant(
    id="var_citroen-c3-1-2-82", generation_id="gen_citroen-c3-2016", engine_id="eng_petrol-1199-60",
    name="1.2 PureTech 82", year_from=2017, year_to=2020, mass_kg=1050, wheelbase_mm=2540, co2_wltp_g_km=128.5,
)
S = Source(id="eea-co2", name="EEA", license="CC-BY-4.0", license_url="https://creativecommons.org/licenses/by/4.0/", license_checked=D)


@pytest.fixture
def st():
    with Store() as s:
        s.put(B, M, G, E, V, S)
        yield s


@pytest.mark.parametrize("o", [B, M, G, E, V, S])
def test_roundtrip(st, o):
    assert st.get(type(o), o.id) == o


def test_get_missing(st):
    assert st.get(Brand, "brand_none") is None


def test_upsert(st):
    st.put(B.model_copy(update={"name": "Citroen SA"}))
    assert st.get(Brand, B.id).name == "Citroen SA"
    assert len(st.find(Brand)) == 1


def test_fk_violation_rolls_back(st):
    bad = Variant(id="var_x", generation_id="gen_none", engine_id=E.id, name="x", year_from=2000)
    with pytest.raises(sqlite3.IntegrityError):
        st.put(Brand(id="brand_new", name="New"), bad)
    assert st.get(Brand, "brand_new") is None


def test_find_children(st):
    st.put(CarModel(id="model_citroen-c4", brand_id=B.id, name="C4"))
    assert [m.id for m in st.find(CarModel, brand_id=B.id)] == ["model_citroen-c3", "model_citroen-c4"]
    assert st.find(Generation, model_id=M.id) == [G]
    assert st.find(Variant, generation_id=G.id, year_from=2017) == [V]
    assert st.find(Variant, generation_id="gen_other") == []


def test_find_enum_filter(st):
    assert st.find(Engine, fuel=Fuel.PETROL) == [E]
    assert st.find(Engine, fuel="diesel") == []


def test_find_unknown_column(st):
    with pytest.raises(ValueError):
        st.find(Brand, colour="red")


def test_provenance(st):
    p = FieldProvenance(
        entity_id=E.id, field="power_kw", last_verified=D,
        evidence=[Evidence(source_id="eea-co2", value=60, url="https://example.org/r/1", retrieved=D),
                  Evidence(source_id="rdw", value=60, retrieved=D)],
    )
    st.put_prov(p)
    got = st.prov(E.id)
    assert got == [p]
    assert got[0].status is Status.CONFIRMED
    assert st.prov("eng_none") == []


def test_provenance_upsert_and_order(st):
    def fp(f, v):
        return FieldProvenance(entity_id=E.id, field=f, last_verified=D, evidence=[Evidence(source_id="eea-co2", value=v, retrieved=D)])
    st.put_prov(fp("power_kw", 60), fp("displacement_cc", 1199))
    st.put_prov(fp("power_kw", 61))
    got = st.prov(E.id)
    assert [g.field for g in got] == ["displacement_cc", "power_kw"]
    assert got[1].evidence[0].value == 61


def test_persistence_and_readonly(tmp_path):
    f = tmp_path / "v.db"
    with Store(f) as s:
        s.put(B)
    with Store(f, ro=True) as r:
        assert r.get(Brand, B.id) == B
        with pytest.raises(sqlite3.OperationalError):
            r.put(Brand(id="brand_new", name="New"))


def test_readonly_missing_file(tmp_path):
    with pytest.raises(sqlite3.OperationalError):
        Store(tmp_path / "none.db", ro=True)


def test_close():
    s = Store()
    s.close()
    with pytest.raises(sqlite3.ProgrammingError):
        s.find(Brand)
