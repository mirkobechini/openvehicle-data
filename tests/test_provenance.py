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
