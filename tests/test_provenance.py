from datetime import date

import pytest
from pydantic import ValidationError

from core.provenance import Evidence, FieldProvenance, Source, Status

D = date(2026, 9, 19)


def src(**k):
    return Source(id="eea-co2", name="EEA", license="CC-BY-4.0", license_url="https://creativecommons.org/licenses/by/4.0/", **k)


def ev(s="eea-co2", v=51, **k):
    return Evidence(source_id=s, value=v, retrieved=D, **k)


def fp(*e):
    return FieldProvenance(entity_id="eng_petrol-1242-51", field="power_kw", evidence=list(e), last_verified=D)


def test_source_usable():
    assert src().usable is False
    assert src(license_checked=D).usable is True


@pytest.mark.parametrize("k", [{"id": "EEA"}, {"id": "a_b"}, {"license_url": "ftp://x"}, {"license": ""}, {"name": ""}])
def test_source_invalid(k):
    d = dict(id="eea-co2", name="EEA", license="CC-BY-4.0", license_url="https://x.org/l")
    with pytest.raises(ValidationError):
        Source(**{**d, **k})


def test_evidence():
    assert ev().url is None
    assert ev(url="https://example.org/r/1").url == "https://example.org/r/1"
    assert ev(v=None).value is None
    assert ev(v="A").value == "A"
    assert isinstance(ev(v=51.5).value, float)


@pytest.mark.parametrize("k", [{"url": "not a url"}, {"s": "Bad_Id"}])
def test_evidence_invalid(k):
    with pytest.raises(ValidationError):
        ev(**k)


def test_single():
    assert fp(ev()).status is Status.SINGLE


def test_same_source_twice_is_single():
    assert fp(ev(), ev()).status is Status.SINGLE


def test_confirmed():
    assert fp(ev(), ev("rdw", 51)).status is Status.CONFIRMED
    assert fp(ev(v=51), ev("rdw", 51.0)).status is Status.CONFIRMED


def test_conflict():
    assert fp(ev(), ev("rdw", 52)).status is Status.CONFLICT


def test_conflict_with_none():
    assert fp(ev(), ev("rdw", None)).status is Status.CONFLICT


def test_no_evidence():
    with pytest.raises(ValidationError):
        fp()


def test_status_serialised():
    assert fp(ev()).model_dump()["status"] == "single_source"


def test_extra_forbidden():
    with pytest.raises(ValidationError):
        FieldProvenance(entity_id="e", field="f", evidence=[ev()], last_verified=D, x=1)


def test_round_trip_ignores_derived_status():
    p = fp(ev(), ev("rdw", 52))
    d = p.model_dump(mode="json")
    assert d["status"] == "conflict"
    assert FieldProvenance.model_validate(d) == p
    assert FieldProvenance.model_validate({**d, "status": "confirmed"}).status is Status.CONFLICT
    assert FieldProvenance.model_validate(p) == p


def fq(f, *vs):
    return FieldProvenance(entity_id="var_x", field=f, evidence=[ev(s, v) for s, v in zip(("eea-co2", "rdw", "eea-co2", "rdw"), vs)], last_verified=D).status


def test_wheelbase_rounding_is_tolerated():
    assert fq("wheelbase_mm", 2305, 2300) is Status.CONFIRMED
    assert fq("wheelbase_mm", 2300, 2310) is Status.CONFIRMED
    assert fq("wheelbase_mm", 2300, 2311) is Status.CONFLICT


def test_mass_tolerance_is_one_kg():
    assert fq("mass_kg", 1045, 1046) is Status.CONFIRMED
    assert fq("mass_kg", 1045, 1047) is Status.CONFLICT


def test_other_fields_are_compared_exactly():
    assert fq("displacement_cc", 999, 1000) is Status.CONFLICT
    assert fq("power_kw", 51, 51) is Status.CONFIRMED


def test_values_of_different_types_conflict():
    assert fq("mass_kg", "1045", 1045) is Status.CONFLICT
