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


def test_all_prov(st):
    def fp(e, f, v):
        return FieldProvenance(entity_id=e, field=f, last_verified=D, evidence=[Evidence(source_id="eea-co2", value=v, retrieved=D)])
    assert st.all_prov() == []
    st.put_prov(fp(V.id, "mass_kg", 1050), fp(E.id, "power_kw", 60), fp(E.id, "displacement_cc", 1199))
    assert [(p.entity_id, p.field) for p in st.all_prov()] == [(E.id, "displacement_cc"), (E.id, "power_kw"), (V.id, "mass_kg")]


def three(st):
    st.put(
        CarModel(id="model_citroen-c4", brand_id=B.id, name="C4", aliases=["C-Quatre"]),
        CarModel(id="model_citroen-c5", brand_id=B.id, name="C5 100%_x"),
    )


def test_pagination(st):
    three(st)
    assert [m.id for m in st.find(CarModel, limit=2)] == ["model_citroen-c3", "model_citroen-c4"]
    assert [m.id for m in st.find(CarModel, limit=2, offset=2)] == ["model_citroen-c5"]
    assert st.find(CarModel, limit=2, offset=5) == []
    assert st.count(CarModel) == 3


def test_count_with_filters(st):
    three(st)
    assert st.count(CarModel, brand_id=B.id) == 3
    assert st.count(CarModel, brand_id="brand_none") == 0
    assert st.count(Brand, q="citro") == 1


def test_search_name_and_alias(st):
    three(st)
    assert [m.id for m in st.find(CarModel, q="c4")] == ["model_citroen-c4"]
    assert [m.id for m in st.find(CarModel, q="quatre")] == ["model_citroen-c4"]
    assert st.find(Brand, q="CITROEN")[0].id == B.id
    assert st.find(Brand, q="Citroën SA")[0].id == B.id
    assert st.find(CarModel, q="zzz") == []


def test_search_escapes_wildcards(st):
    three(st)
    assert [m.id for m in st.find(CarModel, q="100%_x")] == ["model_citroen-c5"]
    assert st.find(CarModel, q="%") == [st.get(CarModel, "model_citroen-c5")]
    assert st.find(CarModel, q="_") == [st.get(CarModel, "model_citroen-c5")]
    assert st.find(CarModel, q="c_") == []


def test_search_combined_with_filters_and_paging(st):
    three(st)
    assert [m.id for m in st.find(CarModel, q="c", brand_id=B.id, limit=1, offset=1)] == ["model_citroen-c4"]


def test_in_filter(st):
    three(st)
    ids = ["model_citroen-c3", "model_citroen-c5", "model_none"]
    assert [m.id for m in st.find(CarModel, id=ids)] == ["model_citroen-c3", "model_citroen-c5"]
    assert [m.id for m in st.find(CarModel, id=("model_citroen-c4",))] == ["model_citroen-c4"]
    assert st.find(CarModel, id=[]) == []
    assert st.count(CarModel, id=set(ids)) == 2


@pytest.mark.parametrize("cls", [Engine, Source])
def test_search_needs_name_and_aliases(st, cls):
    with pytest.raises(ValueError):
        st.find(cls, q="x")
    with pytest.raises(ValueError):
        st.count(cls, q="x")


def test_backup(st, tmp_path):
    f = tmp_path / "b.db"
    st.backup(f)
    with Store(f, ro=True) as r:
        assert r.find(Variant) == [V]
        assert r.get(Brand, B.id) == B
