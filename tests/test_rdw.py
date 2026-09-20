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


def test_query_plates_takes_one_plate_per_variant():
    q = rdw.query_plates(2019, 10, 20)
    assert q["$select"] == "merk,type,variant,uitvoering,min(kenteken) as k" and q["$group"] == q["$order"] == "merk,type,variant,uitvoering"
    assert q["$limit"] == 10 and q["$offset"] == 20 and "20190101" in q["$where"]
    with pytest.raises(ValueError):
        rdw.query_plates("2019")


def test_fetch_pages_the_plate_query(monkeypatch):
    monkeypatch.setattr(rdw, "STEP", 2)
    data, sel = [{"merk": "FIAT", "k": str(i)} for i in range(3)], []

    def h(req):
        sel.append(req.url.params["$select"])
        o, n = int(req.url.params["$offset"]), int(req.url.params["$limit"])
        return httpx.Response(200, json=data[o:o + n])

    assert rdw.fetch(2019, client(h), rdw.query_plates) == data
    assert len(sel) == 2 and all("min(kenteken)" in s for s in sel)


def test_fetch_power_in_batches_keeping_only_power(monkeypatch):
    monkeypatch.setattr(rdw, "BATCH", 2)
    seen = []

    def h(req):
        seen.append((str(req.url).split("?")[0], req.url.params["$select"], req.url.params["$where"]))
        ks = [x.strip("'") for x in req.url.params["$where"][len("kenteken in("):-1].split(",")]
        return httpx.Response(200, json=[{"kenteken": k, "nettomaximumvermogen": "51.50"} for k in ks] + [{"kenteken": ks[0], "nettomaximumvermogen": "62.00"}, {"kenteken": ks[0]}, {"kenteken": ks[0], "nettomaximumvermogen": "0"}])

    r = rdw.fetch_power(["A1", "B2", "C3"], client(h))
    assert r == {"A1": [51.5, 62.0], "B2": [51.5], "C3": [51.5, 62.0]}
    assert len(seen) == 2 and seen[0][0] == rdw.FUEL and seen[0][1] == "kenteken,nettomaximumvermogen"
    assert seen[0][2] == "kenteken in('A1','B2')" and seen[1][2] == "kenteken in('C3')"


def test_fetch_power_ignores_odd_plates():
    seen = []

    def h(req):
        seen.append(req.url.params["$where"])
        return httpx.Response(200, json=[])

    assert rdw.fetch_power(["OK1", "a'b", "", None, "X" * 9, "1) OR (1=1"], client(h)) == {}
    assert seen == ["kenteken in('OK1')"]
    seen.clear()
    assert rdw.fetch_power([], client(h)) == {} and seen == []


@pytest.mark.parametrize("h", [lambda r: httpx.Response(500), lambda r: (_ for _ in ()).throw(httpx.ConnectError("boom"))])
def test_fetch_power_errors_never_show_the_plates(h):
    with pytest.raises(RuntimeError) as e:
        rdw.fetch_power(["SECRET1"], client(h))
    assert "SECRET1" not in str(e.value) and "SECRET1" not in repr(e.value.__cause__) and e.value.__suppress_context__


def test_fetch_power_closes_only_its_own_client(monkeypatch):
    c = client(lambda r: httpx.Response(200, json=[]))
    rdw.fetch_power(["A1"], c)
    assert not c.is_closed
    own = client(lambda r: httpx.Response(200, json=[]))
    monkeypatch.setattr(rdw.httpx, "Client", lambda **k: own)
    rdw.fetch_power(["A1"])
    assert own.is_closed


def test_fold_power_joins_plates_back_to_variants():
    pl = [{"merk": "MERCEDES-BENZ", "type": "1", "variant": "2", "uitvoering": "3", "k": "A1"}, {"merk": "FIAT", "type": "4", "variant": "5", "uitvoering": "6", "k": "B2"}, {"merk": None, "type": "7", "variant": "8", "uitvoering": "9", "k": "C3"}]
    assert rdw.fold_power(pl, {"A1": [62.0, 51.5, 62.0], "C3": [40.0]}) == {("mercedesbenz", "1", "2", "3"): [51.5, 62.0], ("", "7", "8", "9"): [40.0]}


def pw(*v, **k):
    return {("fiat", "312", "A", "B"): {"power_kw": list(v)}} | k


def eng(st, name="312 A B"):
    v = next(x for x in st.find(Variant) if x.name == name)
    return next(p for p in st.prov(v.engine_id) if p.field == "power_kw")


def test_verify_confirms_power_within_a_kilowatt(st):
    s = rdw.verify(st, pw(51.5), TODAY)
    p = eng(st)
    assert p.status is Status.CONFIRMED and [e.source_id for e in p.evidence] == ["eea-co2", "rdw-nl"] and p.evidence[1].value == 51.5
    assert s == {"variants": 3, "matched": 1, "fields": 1, "confirmed": 1, "conflicts": 0}


def test_verify_uses_the_value_closest_to_the_engine_for_hybrids(st):
    rdw.verify(st, pw(110.0, 52.0, 60.0), TODAY)
    p = eng(st)
    assert p.evidence[1].value == 52.0 and p.status is Status.CONFIRMED


def test_verify_flags_a_power_difference(st):
    s = rdw.verify(st, pw(70.0), TODAY)
    assert eng(st).status is Status.CONFLICT and s["conflicts"] == 1


def test_verify_skips_missing_power(st):
    assert rdw.verify(st, pw(), TODAY)["fields"] == 0
    assert eng(st).status is Status.SINGLE


def test_verify_adds_power_once_per_value_for_a_shared_engine(st):
    fo = pw(52.0) | {("fiat", "312", "C", "D"): {"power_kw": [52.0]}}
    rdw.verify(st, fo, TODAY)
    assert [e.source_id for e in eng(st).evidence] == ["eea-co2", "rdw-nl"]


def test_verify_skips_power_when_the_engine_has_none(tmp_path):
    with Store(tmp_path / "n.db") as s:
        eea.load([erow(ep=None)], s, 2025, TODAY)
        assert rdw.verify(s, pw(52.0), TODAY)["fields"] == 0


def test_run_confirms_power_through_the_plates(tmp_path):
    db = tmp_path / "r.db"
    with Store(db) as s:
        eea.load([erow()], s, 2025, TODAY)
    plates = [{"merk": "FIAT", "type": "312", "variant": "A", "uitvoering": "B", "k": "AB123C"}]
    fuel = [{"kenteken": "AB123C", "nettomaximumvermogen": "52.00"}]
    r = rdw.run(db, 2019, rclient([rrow()], plates, fuel), TODAY)
    assert r["matched"] == 1 and r["confirmed"] == 4
    with Store(db, ro=True) as s:
        v = next(x for x in s.find(Variant))
        p = next(p for p in s.prov(v.engine_id) if p.field == "power_kw")
        assert p.status is Status.CONFIRMED and p.evidence[1].value == 52.0


def test_run_keeps_working_when_only_power_matches(tmp_path):
    db = tmp_path / "r.db"
    with Store(db) as s:
        eea.load([erow()], s, 2025, TODAY)
    plates = [{"merk": "FIAT", "type": "312", "variant": "A", "uitvoering": "B", "k": "AB123C"}]
    r = rdw.run(db, 2019, rclient([], plates, [{"kenteken": "AB123C", "nettomaximumvermogen": "52.00"}]), TODAY)
    assert r["matched"] == 1 and r["fields"] == 1
