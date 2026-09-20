from datetime import date

import httpx
import pytest

from core.models import Variant
from core.provenance import Status
from core.storage import Store
from pipeline.importers import eea, rdw
from pipeline.validation import Severity, validate

TODAY = date(2026, 9, 20)


def erow(**k):
    return {
        "Mk": "FIAT", "Cn": "PANDA", "T": "312", "Va": "A", "Ve": "B", "Ft": "petrol", "Fm": "M",
        "ec": 999, "ep": 52, "m": 1000, "w": 2300, "at1": None, "co2": 100, "n": 1, **k,
    }


def rrow(**k):
    return {"merk": "FIAT", "type": "312", "variant": "A", "uitvoering": "B", "massa_rijklaar": "1000", "cilinderinhoud": "999", "wielbasis": "230", "n": "5", **k}


def client(h):
    return httpx.Client(transport=httpx.MockTransport(h))


def rclient(main=None, plates=None, fuel=None):
    def h(req):
        if req.url.path.endswith("8ys7-d773.json"):
            return httpx.Response(200, json=fuel or [])
        if "min(kenteken)" in req.url.params["$select"]:
            return httpx.Response(200, json=plates or [])
        return httpx.Response(200, json=main or [])

    return client(h)


@pytest.fixture
def st(tmp_path):
    with Store(tmp_path / "v.db") as s:
        eea.load([erow(), erow(Va="C", Ve="D", w=None), erow(Va="E", Ve="F", ec=1200)], s, 2025, TODAY)
        yield s


def status(st, name, f):
    v = next(x for x in st.find(Variant) if x.name == name)
    return next(p for p in st.prov(v.id) if p.field == f)


def test_query():
    q = rdw.query(2019, 10, 20)
    assert q["$limit"] == 10 and q["$offset"] == 20 and "20190101" in q["$where"] and "M1" in q["$where"]
    assert q["$group"] == q["$order"] and q["$select"].endswith("count(*) as n")


@pytest.mark.parametrize("y", [None, "2019", 1800, 2200])
def test_query_bad_year(y):
    with pytest.raises(ValueError):
        rdw.query(y)


def test_fetch_pages_until_a_short_page(monkeypatch):
    monkeypatch.setattr(rdw, "STEP", 2)
    data, seen = [rrow(type=str(i)) for i in range(5)], []

    def h(req):
        o, n = int(req.url.params["$offset"]), int(req.url.params["$limit"])
        seen.append((o, n, req.headers["user-agent"]))
        return httpx.Response(200, json=data[o:o + n])

    assert rdw.fetch(2019, client(h)) == data
    assert seen == [(0, 2, rdw.UA), (2, 2, rdw.UA), (4, 2, rdw.UA)]


def test_fetch_stops_after_an_empty_page(monkeypatch):
    monkeypatch.setattr(rdw, "STEP", 1)
    data = [rrow()]
    h = lambda req: httpx.Response(200, json=data[int(req.url.params["$offset"]):][:1])
    assert rdw.fetch(2019, client(h)) == data


def test_fetch_http_error():
    with pytest.raises(httpx.HTTPStatusError):
        rdw.fetch(2019, client(lambda r: httpx.Response(500)))


def test_fetch_closes_only_its_own_client(monkeypatch):
    c = client(lambda r: httpx.Response(200, json=[]))
    assert rdw.fetch(2019, c) == [] and not c.is_closed
    own = client(lambda r: httpx.Response(200, json=[]))
    monkeypatch.setattr(rdw.httpx, "Client", lambda **k: own)
    assert rdw.fetch(2019) == [] and own.is_closed


def test_fold_takes_the_most_common_value_per_field():
    r = rdw.fold([rrow(massa_rijklaar="1000", n="2"), rrow(massa_rijklaar="1010", n="9"), rrow(cilinderinhoud="998", n="1")])
    assert r == {("fiat", "312", "A", "B"): {"mass_kg": 1010.0, "displacement_cc": 999, "wheelbase_mm": 2300}}


def test_fold_breaks_ties_with_the_smaller_value():
    r = rdw.fold([rrow(massa_rijklaar="1010", n="3"), rrow(massa_rijklaar="1000", n="3")])
    assert r[("fiat", "312", "A", "B")]["mass_kg"] == 1000.0


def test_fold_ignores_missing_and_invalid_values():
    r = rdw.fold([rrow(massa_rijklaar=None, cilinderinhoud="x", wielbasis="0")])
    assert r == {}
    r = rdw.fold([rrow(cilinderinhoud=None), {"type": "1", "variant": "2", "uitvoering": "3", "massa_rijklaar": "900", "n": "1"}])
    assert r[("fiat", "312", "A", "B")] == {"mass_kg": 1000.0, "wheelbase_mm": 2300}
    assert r[("", "1", "2", "3")] == {"mass_kg": 900.0}


def test_fold_normalises_the_make():
    assert ("mercedesbenz", "1", "2", "3") in rdw.fold([rrow(merk="MERCEDES-BENZ", type="1", variant="2", uitvoering="3")])


def test_verify_confirms_matching_values(st):
    s = rdw.verify(st, rdw.fold([rrow()]), TODAY)
    assert s == {"variants": 3, "matched": 1, "fields": 3, "confirmed": 3, "conflicts": 0}
    p = status(st, "312 A B", "mass_kg")
    assert p.status is Status.CONFIRMED and p.last_verified == TODAY
    assert [e.source_id for e in p.evidence] == ["eea-co2", "rdw-nl"] and p.evidence[1].url == rdw.PAGE
    assert p.evidence[1].value == 1000.0


def test_verify_tolerates_wheelbase_rounding(st):
    rdw.verify(st, rdw.fold([rrow(wielbasis="231")]), TODAY)
    p = status(st, "312 A B", "wheelbase_mm")
    assert p.status is Status.CONFIRMED and p.evidence[1].value == 2310


def test_verify_flags_real_disagreements(st):
    s = rdw.verify(st, rdw.fold([rrow(massa_rijklaar="1020", wielbasis="250")]), TODAY)
    assert s["conflicts"] == 2 and s["confirmed"] == 1
    assert status(st, "312 A B", "mass_kg").status is Status.CONFLICT


def test_verify_skips_unmatched_and_odd_names(st):
    s = rdw.verify(st, rdw.fold([rrow(type="999"), rrow(merk="OPEL")]), TODAY)
    assert s["matched"] == 0 and s["fields"] == 0
    assert status(st, "312 A B", "mass_kg").status is Status.SINGLE


def test_verify_needs_a_value_on_both_sides(st):
    rdw.verify(st, rdw.fold([rrow(Va="C", variant="C", uitvoering="D", massa_rijklaar=None)]), TODAY)
    assert status(st, "312 C D", "mass_kg").status is Status.SINGLE
    v = next(x for x in st.find(Variant) if x.name == "312 C D")
    assert [p.field for p in st.prov(v.id)] == ["co2_wltp_g_km", "mass_kg"]


def test_verify_adds_the_engine_evidence_once_per_value(st):
    rdw.verify(st, rdw.fold([rrow(), rrow(variant="C", uitvoering="D")]), TODAY)
    v = next(x for x in st.find(Variant) if x.name == "312 A B")
    p = next(p for p in st.prov(v.engine_id) if p.field == "displacement_cc")
    assert [e.source_id for e in p.evidence] == ["eea-co2", "rdw-nl"] and p.status is Status.CONFIRMED


def test_verify_keeps_both_values_when_variants_of_one_engine_disagree(st):
    rdw.verify(st, rdw.fold([rrow(), rrow(variant="C", uitvoering="D", cilinderinhoud="1000")]), TODAY)
    v = next(x for x in st.find(Variant) if x.name == "312 A B")
    p = next(p for p in st.prov(v.engine_id) if p.field == "displacement_cc")
    assert [e.value for e in p.evidence] == [999, 999, 1000] and p.status is Status.CONFLICT


def test_verify_skips_fields_without_provenance(st):
    v = next(x for x in st.find(Variant) if x.name == "312 A B")
    st.c.execute("DELETE FROM provenance WHERE entity_id=? AND field='mass_kg'", (v.id,))
    s = rdw.verify(st, rdw.fold([rrow()]), TODAY)
    assert s["fields"] == 2


def test_verify_registers_the_source_and_the_result_validates(st):
    rdw.verify(st, rdw.fold([rrow(), rrow(variant="E", uitvoering="F", massa_rijklaar="1050")]), TODAY)
    assert st.get(type(rdw.RDW), "rdw-nl") == rdw.RDW
    vs = validate(st)
    assert [v.rule for v in vs] == ["source_conflict"] * 2 and {v.severity for v in vs} == {Severity.WARNING}


def test_verify_matches_on_brand_aliases(st):
    rdw.verify(st, rdw.fold([rrow(merk="fiat")]), TODAY)
    assert status(st, "312 A B", "mass_kg").status is Status.CONFIRMED


def test_run(tmp_path):
    db = tmp_path / "r.db"
    with Store(db) as s:
        eea.load([erow()], s, 2025, TODAY)
    r = rdw.run(db, 2019, rclient([rrow()]), TODAY)
    assert r["matched"] == 1 and r["confirmed"] == 3


def test_main(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(rdw, "run", lambda *a: calls.append(a) or {"ok": 1})
    rdw.main(["--db", "x.db"])
    rdw.main(["--db", "y.db", "--since", "2021"])
    assert calls == [("x.db", 2019), ("y.db", 2021)]
