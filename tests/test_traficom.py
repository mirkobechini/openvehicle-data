import io
import zipfile
from datetime import date

import httpx
import pytest

from core.models import Variant
from core.provenance import Evidence, FieldProvenance, Status
from core.storage import Store
from pipeline.importers import eea, traficom
from pipeline.validation import validate

TODAY = date(2026, 10, 20)

HEADER = "ajoneuvoluokka;merkkiSelvakielinen;variantti;versio;tyyppihyvaksyntanro;omamassa;teknSuurSallKokmassa;istumapaikkojenLkm;iskutilavuus;suurinNettoteho"
FIELDS = ["ajoneuvoluokka", "merkkiSelvakielinen", "variantti", "versio", "tyyppihyvaksyntanro", "omamassa", "teknSuurSallKokmassa", "istumapaikkojenLkm", "iskutilavuus", "suurinNettoteho"]


def trow(**k):
    d = {
        "ajoneuvoluokka": "M1", "merkkiSelvakielinen": "FIAT", "variantti": "A", "versio": "B",
        "tyyppihyvaksyntanro": "E3*2007/46*0064*01", "omamassa": "1000", "teknSuurSallKokmassa": "1400",
        "istumapaikkojenLkm": "5", "iskutilavuus": "999", "suurinNettoteho": "52", **k,
    }
    return ";".join(str(d[f]) for f in FIELDS)


def zipped(*lines):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("TieliikenneAvoinData.csv", "\n".join([HEADER, *lines]).encode("cp1252"))
    return buf.getvalue()


def client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def zclient(*lines):
    return client(lambda r: httpx.Response(200, content=zipped(*lines)))


def erow(**k):
    return {
        "Mk": "FIAT", "Cn": "PANDA", "T": "312", "Va": "A", "Ve": "B", "Ft": "petrol", "Fm": "M",
        "ec": 999, "ep": 52, "m": 1000, "w": 2300, "at1": None, "co2": 100, "n": 1, "ta": "E3*2007/46*0064*01", **k,
    }


@pytest.fixture
def st(tmp_path):
    with Store(tmp_path / "v.db") as s:
        eea.load([erow()], s, 2025, TODAY)
        yield s


def status(st, name, f):
    v = next(x for x in st.find(Variant) if x.name == name)
    return next(p for p in st.prov(v.id) if p.field == f)


def test_rows_keeps_only_m1():
    rs = list(traficom.rows(zipped(trow(), trow(ajoneuvoluokka="N1"))))
    assert len(rs) == 1 and rs[0]["merkkiSelvakielinen"] == "FIAT"


def test_fold_takes_the_most_common_value_and_ties_the_lowest():
    rows = traficom.rows(zipped(trow(omamassa="1000"), trow(omamassa="1000"), trow(omamassa="1100")))
    fo = traficom.fold(rows)
    k = ("fiat", "e3*2007/46*0064", "A", "B")
    assert fo[k]["mass_kg"] == 1000.0
    rows = traficom.rows(zipped(trow(omamassa="1000", teknSuurSallKokmassa="1400"), trow(omamassa="1100", teknSuurSallKokmassa="1400")))
    assert traficom.fold(rows)[k]["max_mass_kg"] == 1400.0


def test_fold_skips_rows_without_a_type_approval():
    rows = traficom.rows(zipped(trow(tyyppihyvaksyntanro=""), trow(tyyppihyvaksyntanro="garbage")))
    assert traficom.fold(rows) == {}


def test_fold_ignores_blank_and_non_positive_numbers():
    rows = traficom.rows(zipped(trow(omamassa="", istumapaikkojenLkm="0", suurinNettoteho="abc")))
    k = ("fiat", "e3*2007/46*0064", "A", "B")
    fo = traficom.fold(rows)
    assert "mass_kg" not in fo[k] and "seats" not in fo[k] and "power_kw" not in fo[k]
    assert fo[k]["max_mass_kg"] == 1400.0


def test_fold_keys_on_brand_approval_variant_and_version():
    rows = traficom.rows(zipped(trow(merkkiSelvakielinen="FIAT-Italia"), trow(variantti="C"), trow(tyyppihyvaksyntanro="E3*2007/46*0099*01")))
    fo = traficom.fold(rows)
    assert len(fo) == 3
    assert ("fiatitalia", "e3*2007/46*0064", "A", "B") in fo
    assert ("fiat", "e3*2007/46*0064", "C", "B") in fo
    assert ("fiat", "e3*2007/46*0099", "A", "B") in fo


def test_verify_confirms_mass_displacement_and_power(st):
    fo = traficom.fold(traficom.rows(zipped(trow())))
    r = traficom.verify(st, fo, TODAY)
    assert r == {"variants": 1, "matched": 1, "fields": 5, "confirmed": 3, "conflicts": 0}
    p = status(st, "312 A B", "mass_kg")
    assert p.status is Status.CONFIRMED and [e.source_id for e in p.evidence] == ["eea-co2", "traficom-fi"]
    v = next(x for x in st.find(Variant) if x.name == "312 A B")
    ep = next(p for p in st.prov(v.engine_id) if p.field == "displacement_cc")
    assert ep.status is Status.CONFIRMED and [e.source_id for e in ep.evidence] == ["eea-co2", "traficom-fi"]
    assert validate(st) == []


def test_verify_fills_seats_and_max_mass(st):
    fo = traficom.fold(traficom.rows(zipped(trow(istumapaikkojenLkm="5", teknSuurSallKokmassa="1400"))))
    traficom.verify(st, fo, TODAY)
    v = next(x for x in st.find(Variant) if x.name == "312 A B")
    assert (v.seats, v.max_mass_kg) == (5, 1400.0)
    p = status(st, "312 A B", "seats")
    assert p.status is Status.SINGLE and p.evidence[0].source_id == "traficom-fi"


def test_verify_does_not_overwrite_existing_seats(st):
    v = next(x for x in st.find(Variant) if x.name == "312 A B")
    st.put(v.model_copy(update={"seats": 4}))
    st.put_prov(FieldProvenance(entity_id=v.id, field="seats", evidence=[Evidence(source_id="rdw-nl", value=4, retrieved=TODAY)], last_verified=TODAY))
    traficom.verify(st, traficom.fold(traficom.rows(zipped(trow(istumapaikkojenLkm="5")))), TODAY)
    assert next(x for x in st.find(Variant) if x.name == "312 A B").seats == 4


def test_verify_adds_the_engine_evidence_once_per_value(tmp_path):
    with Store(tmp_path / "x.db") as s:
        eea.load([erow(), erow(Va="C", Ve="D")], s, 2025, TODAY)
        traficom.verify(s, traficom.fold(traficom.rows(zipped(trow(), trow(variantti="C")))), TODAY)
        v = next(x for x in s.find(Variant) if x.name == "312 A B")
        p = next(p for p in s.prov(v.engine_id) if p.field == "displacement_cc")
        assert [e.source_id for e in p.evidence] == ["eea-co2", "traficom-fi"] and p.status is Status.CONFIRMED


def test_add_skips_a_field_with_no_existing_provenance(st):
    v = next(x for x in st.find(Variant) if x.name == "312 A B")
    out = {}
    traficom._add(st, v.id, "max_mass_kg", 1400.0, TODAY, set(), out)
    assert out == {}


def test_add_skips_a_missing_value(st):
    v = next(x for x in st.find(Variant) if x.name == "312 A B")
    out = {}
    traficom._add(st, v.id, "mass_kg", None, TODAY, set(), out)
    assert out == {}


def test_verify_flags_a_conflicting_mass(st):
    traficom.verify(st, traficom.fold(traficom.rows(zipped(trow(omamassa="2000")))), TODAY)
    assert status(st, "312 A B", "mass_kg").status is Status.CONFLICT
    assert [v.rule for v in validate(st)] == ["source_conflict"]


def test_verify_requires_the_matching_codes(tmp_path):
    with Store(tmp_path / "x.db") as s:
        eea.load([erow(Va=None)], s, 2025, TODAY)
        r = traficom.verify(s, traficom.fold(traficom.rows(zipped(trow()))), TODAY)
        assert r["matched"] == 0 and r["variants"] == 1


def test_verify_only_confirms_fields_the_variant_already_has(tmp_path):
    with Store(tmp_path / "x.db") as s:
        eea.load([erow(ec=None, ep=None, m=None)], s, 2025, TODAY)
        r = traficom.verify(s, traficom.fold(traficom.rows(zipped(trow()))), TODAY)
        assert r["fields"] == 2


def test_run_builds_the_dataset_and_cross_checks(tmp_path):
    db = tmp_path / "r.db"
    with Store(db) as s:
        eea.load([erow()], s, 2025, TODAY)
    r = traficom.run(db, zclient(trow()), TODAY)
    assert r["matched"] == 1
    with Store(db, ro=True) as s:
        assert validate(s) == []


def test_fetch():
    data = zipped(trow())
    assert traficom.fetch(zclient(trow())) == data


def test_fetch_does_not_send_an_accept_header_the_server_rejects_with_406():
    # opendata.traficom.fi returns 406 for "Accept: application/zip", found on the real file.
    seen = {}

    def h(r):
        seen.update(r.headers)
        return httpx.Response(200, content=zipped(trow()))

    traficom.fetch(client(h))
    assert seen["accept"] == "*/*" and seen["user-agent"] == traficom.UA


def test_fetch_retries_a_server_error():
    data = zipped(trow())
    calls = []

    def h(r):
        calls.append(1)
        return httpx.Response(500) if len(calls) == 1 else httpx.Response(200, content=data)

    assert traficom.fetch(client(h)) == data and len(calls) == 2


def test_fetch_raises_on_a_permanent_error():
    with pytest.raises(httpx.HTTPStatusError):
        traficom.fetch(client(lambda r: httpx.Response(404)))


def test_fetch_closes_only_its_own_client(monkeypatch):
    data = zipped(trow())
    c = zclient(trow())
    traficom.fetch(c)
    assert not c.is_closed
    own = zclient(trow())
    monkeypatch.setattr(traficom.httpx, "Client", lambda **k: own)
    traficom.fetch()
    assert own.is_closed


def test_rows_reads_the_finnish_encoding():
    rs = list(traficom.rows(zipped(trow(merkkiSelvakielinen="Citro\xebn"))))
    assert rs[0]["merkkiSelvakielinen"] == "Citro\xebn"


def test_rows_is_a_generator_not_a_list():
    import types

    assert isinstance(traficom.rows(zipped(trow())), types.GeneratorType)


def test_main(monkeypatch, capsys, tmp_path):
    db = tmp_path / "m.db"
    with Store(db) as s:
        eea.load([erow()], s, 2025, TODAY)
    own = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=zipped(trow()))))
    monkeypatch.setattr(traficom.httpx, "Client", lambda **k: own)
    traficom.main(["--db", str(db)])
    assert "'matched': 1" in capsys.readouterr().out
