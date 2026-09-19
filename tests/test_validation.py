from datetime import date

import pytest

from core.models import Brand, CarModel, Engine, Generation, Variant
from core.provenance import Evidence, FieldProvenance, Source
from core.storage import Store
from pipeline.validation import BuildError, Severity, ensure, report, validate

D = date(2026, 9, 19)
SRC = Source(id="eea-co2", name="EEA", license="CC-BY-4.0", license_url="https://x.org/l", license_checked=D)
RDW = Source(id="rdw", name="RDW", license="CC0-1.0", license_url="https://x.org/l", license_checked=D)


def ev(v, s="eea-co2"):
    return Evidence(source_id=s, value=v, retrieved=D)


def pv(eid, f, *e):
    return FieldProvenance(entity_id=eid, field=f, last_verified=D, evidence=list(e))


def build(ek=None, vk=None, srcs=(SRC,), prov=True):
    st = Store()
    e = Engine(id="eng_petrol-1199-60", **{"fuel": "petrol", "displacement_cc": 1199, "power_kw": 60, **(ek or {})})
    v = Variant(
        id="var_c3-a", generation_id="gen_c3", engine_id=e.id, name="1.2", year_from=2017, year_to=2020,
        **{"mass_kg": 1050, "wheelbase_mm": 2540, **(vk or {})},
    )
    st.put(
        Brand(id="brand_citroen", name="Citroën"),
        CarModel(id="model_c3", brand_id="brand_citroen", name="C3"),
        Generation(id="gen_c3", model_id="model_c3", name="III", year_from=2016, year_to=2021),
        e, v, *srcs,
    )
    if prov:
        for o in (e, v):
            for f in ("displacement_cc", "power_kw", "mass_kg", "wheelbase_mm"):
                if getattr(o, f, None) is not None:
                    st.put_prov(pv(o.id, f, ev(getattr(o, f))))
    return st


def rules(st):
    return [v.rule for v in validate(st)]


def test_clean():
    st = build()
    assert validate(st) == []
    assert report([]) == "no violations"
    assert ensure(st) == []


def test_missing_optional_fields_are_clean():
    assert validate(build(vk={"mass_kg": None, "wheelbase_mm": None})) == []


@pytest.mark.parametrize("vk,ek", [
    ({"mass_kg": 100}, None), ({"mass_kg": 6000}, None),
    ({"wheelbase_mm": 900}, None), (None, {"power_kw": 1500}),
])
def test_implausible(vk, ek):
    assert rules(build(ek=ek, vk=vk)) == ["implausible_value"]


def test_plausible_boundaries():
    assert validate(build(vk={"mass_kg": 400, "wheelbase_mm": 4000}, ek={"power_kw": 1000})) == []


def test_units_litres():
    assert rules(build(ek={"displacement_cc": 2})) == ["unit"]


def test_units_electric_ok():
    assert validate(build(ek={"fuel": "electric", "displacement_cc": 0})) == []


def test_brand_duplicate():
    st = build()
    st.put(Brand(id="brand_citroen-2", name="CITROEN"))
    vs = [v for v in validate(st) if v.rule == "brand_duplicate"]
    assert {v.entity_id for v in vs} == {"brand_citroen", "brand_citroen-2"}
    assert all(v.severity is Severity.ERROR for v in vs)


def test_brand_alias_clash():
    st = build()
    st.put(Brand(id="brand_ds", name="DS", aliases=["Citroen"]))
    assert rules(st) == ["brand_duplicate", "brand_duplicate"]


def test_model_duplicate_only_within_brand():
    st = build()
    st.put(Brand(id="brand_ds", name="DS"), CarModel(id="model_ds-c3", brand_id="brand_ds", name="C3"))
    assert validate(st) == []
    st.put(CarModel(id="model_c3-b", brand_id="brand_citroen", name="c3"))
    assert rules(st) == ["model_duplicate", "model_duplicate"]


def test_variant_duplicate():
    st = build()
    st.put(Variant(id="var_c3-b", generation_id="gen_c3", engine_id="eng_petrol-1199-60", name="1.2", year_from=2017, year_to=2020))
    assert rules(st) == ["variant_duplicate", "variant_duplicate"]


@pytest.mark.parametrize("y", [(2010, 2020), (2017, 2025), (2017, None)])
def test_variant_years(y):
    st = build()
    st.put(Variant(id="var_c3-y", generation_id="gen_c3", engine_id="eng_petrol-1199-60", name="y", year_from=y[0], year_to=y[1]))
    assert rules(st) == ["variant_years"]


def test_variant_years_open_generation():
    st = Store()
    st.put(
        Brand(id="brand_a", name="A"), CarModel(id="model_a", brand_id="brand_a", name="A"),
        Generation(id="gen_a", model_id="model_a", name="I", year_from=2020),
        Engine(id="eng_e", fuel="electric"),
        Variant(id="var_a", generation_id="gen_a", engine_id="eng_e", name="v", year_from=2021),
    )
    assert validate(st) == []


def test_missing_provenance():
    st = build(prov=False)
    vs = validate(st)
    assert {v.rule for v in vs} == {"missing_provenance"}
    assert len(vs) == 4


def test_unknown_source():
    assert set(rules(build(srcs=()))) == {"unknown_source"}


def test_unlicensed_source():
    assert set(rules(build(srcs=(SRC.model_copy(update={"license_checked": None}),)))) == {"unlicensed_source"}


def test_value_unsupported():
    st = build()
    st.put_prov(pv("eng_petrol-1199-60", "power_kw", ev(99)))
    assert rules(st) == ["value_unsupported"]


def test_conflict_is_warning():
    st = build(srcs=(SRC, RDW))
    st.put_prov(pv("eng_petrol-1199-60", "power_kw", ev(60), ev(61, "rdw")))
    vs = validate(st)
    assert [(v.rule, v.severity) for v in vs] == [("source_conflict", Severity.WARNING)]
    assert ensure(st) == vs


def test_ensure_raises_on_error():
    with pytest.raises(BuildError) as ei:
        ensure(build(prov=False))
    assert len(ei.value.violations) == 4
    assert "missing_provenance" in str(ei.value)


def test_ensure_returns_warnings():
    vs = ensure(build(vk={"mass_kg": 100}))
    assert [v.rule for v in vs] == ["implausible_value"]


def test_errors_sorted_first():
    st = build(prov=False, vk={"mass_kg": 100})
    sev = [v.severity for v in validate(st)]
    assert sev == sorted(sev, key=lambda s: s != Severity.ERROR)
    assert sev[0] is Severity.ERROR and sev[-1] is Severity.WARNING


def test_report():
    out = report(validate(build(prov=False, vk={"mass_kg": 100})))
    assert out.splitlines()[-1] == "4 errors, 1 warnings"
    assert out.startswith("ERROR missing_provenance")
    assert "WARNING implausible_value var_c3-a: mass_kg=100" in out
