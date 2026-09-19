import sqlite3
from datetime import date

import pytest

from core.enums import Fuel
from core.models import Brand, CarModel, Engine, Family, Generation, Variant
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


def test_registrations_round_trip(st):
    m = M.model_copy(update={"registrations": 120})
    v = V.model_copy(update={"registrations": 7})
    st.put(m, v)
    assert st.get(CarModel, M.id).registrations == 120
    assert st.get(Variant, V.id).registrations == 7


def test_registrations_default_is_null(st):
    assert st.get(CarModel, M.id).registrations is None
    assert st.get(Variant, V.id).registrations is None


def test_unknown_columns_are_ignored_when_reading(st):
    st.c.execute("ALTER TABLE brands ADD COLUMN note TEXT")
    st.c.execute("UPDATE brands SET note = 'x'")
    assert st.get(Brand, B.id) == B
    assert st.find(Brand) == [B]


def regs(st):
    st.put(
        CarModel(id="model_citroen-c4", brand_id=B.id, name="C4", registrations=50),
        CarModel(id="model_citroen-c5", brand_id=B.id, name="C5", registrations=900),
        CarModel(id="model_citroen-c6", brand_id=B.id, name="C6", registrations=50),
        M.model_copy(update={"registrations": None}),
    )


def test_sort_by_registrations_descending(st):
    regs(st)
    assert [m.id for m in st.find(CarModel, sort="-registrations")] == [
        "model_citroen-c5", "model_citroen-c4", "model_citroen-c6", "model_citroen-c3",
    ]


def test_sort_ascending_and_default(st):
    regs(st)
    assert [m.id for m in st.find(CarModel, sort="registrations")][0] == "model_citroen-c3"
    assert [m.id for m in st.find(CarModel, sort="-name")][0] == "model_citroen-c6"
    assert [m.id for m in st.find(CarModel)] == ["model_citroen-c3", "model_citroen-c4", "model_citroen-c5", "model_citroen-c6"]


def test_sort_with_paging(st):
    regs(st)
    assert [m.id for m in st.find(CarModel, sort="-registrations", limit=2, offset=1)] == ["model_citroen-c4", "model_citroen-c6"]


def test_minimum_filter(st):
    regs(st)
    assert [m.id for m in st.find(CarModel, registrations__gte=50, sort="-registrations")] == [
        "model_citroen-c5", "model_citroen-c4", "model_citroen-c6",
    ]
    assert [m.id for m in st.find(CarModel, registrations__gte=51)] == ["model_citroen-c5"]
    assert st.count(CarModel, registrations__gte=50) == 3
    assert st.count(CarModel, registrations__gte=0) == 3
    assert st.count(CarModel, registrations__gte=1000) == 0


def test_minimum_filter_combines_with_search_and_equality(st):
    regs(st)
    assert [m.id for m in st.find(CarModel, q="c", registrations__gte=100, brand_id=B.id)] == ["model_citroen-c5"]


@pytest.mark.parametrize("kw", [{"sort": "colour"}, {"sort": "-colour"}])
def test_unknown_sort_column(st, kw):
    with pytest.raises(ValueError, match="unknown sort column"):
        st.find(CarModel, **kw)


def test_unknown_minimum_column(st):
    with pytest.raises(ValueError, match="unknown columns"):
        st.find(CarModel, nope__gte=1)
    with pytest.raises(ValueError, match="unknown columns"):
        st.count(CarModel, nope__gte=1)


def test_ids_are_sorted_and_per_type(st):
    three(st)
    assert st.ids(CarModel) == ["model_citroen-c3", "model_citroen-c4", "model_citroen-c5"]
    assert st.ids(Brand) == [B.id]
    assert st.ids(Variant) == [V.id] and st.ids(Engine) == [E.id] and st.ids(Source) == [S.id]


def test_ids_of_an_empty_table():
    with Store() as s:
        assert s.ids(Brand) == []


F = Family(id="family_citroen-c3", brand_id=B.id, name="C3", aliases=["C-3"], model_count=2, registrations=500)


def with_family(st):
    st.put(F, M.model_copy(update={"family_id": F.id}), CarModel(id="model_citroen-c3-aircross", brand_id=B.id, name="C3 AIRCROSS", family_id=F.id))


def test_family_round_trip_and_defaults(st):
    st.put(F)
    assert st.get(Family, F.id) == F
    assert st.get(CarModel, M.id).family_id is None


def test_model_family_id_round_trip(st):
    with_family(st)
    assert st.get(CarModel, M.id).family_id == F.id
    assert [m.id for m in st.find(CarModel, family_id=F.id)] == ["model_citroen-c3", "model_citroen-c3-aircross"]
    assert st.find(CarModel, family_id="family_none") == []
    assert st.count(CarModel, family_id=F.id) == 2


def test_a_model_needs_an_existing_family(st):
    with pytest.raises(sqlite3.IntegrityError):
        st.put(M.model_copy(update={"family_id": "family_citroen-none"}))


def test_a_family_needs_an_existing_brand(st):
    with pytest.raises(sqlite3.IntegrityError):
        st.put(F.model_copy(update={"brand_id": "brand_none"}))


def test_families_are_searchable_sortable_and_countable(st):
    st.put(F, Family(id="family_citroen-c4", brand_id=B.id, name="C4", model_count=1, registrations=900),
           Family(id="family_citroen-c5", brand_id=B.id, name="C5", model_count=1))
    assert [f.id for f in st.find(Family, sort="-registrations")] == ["family_citroen-c4", "family_citroen-c3", "family_citroen-c5"]
    assert [f.id for f in st.find(Family, q="c-3")] == ["family_citroen-c3"]
    assert [f.id for f in st.find(Family, registrations__gte=600)] == ["family_citroen-c4"]
    assert st.count(Family, brand_id=B.id) == 3 and st.ids(Family) == ["family_citroen-c3", "family_citroen-c4", "family_citroen-c5"]


def test_families_survive_a_backup(st, tmp_path):
    with_family(st)
    st.backup(tmp_path / "f.db")
    with Store(tmp_path / "f.db", ro=True) as r:
        assert r.get(Family, F.id) == F and r.get(CarModel, M.id).family_id == F.id


def test_has_reports_whether_a_type_has_its_table(st):
    assert all(st.has(c) for c in (Brand, CarModel, Family, Generation, Engine, Variant, Source))
    st.c.execute("PRAGMA foreign_keys=OFF")
    st.c.execute("DROP TABLE families")
    assert st.has(Family) is False and st.has(Brand) is True
