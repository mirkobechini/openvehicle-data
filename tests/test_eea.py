import json
from collections import Counter
from datetime import date
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from core.enums import Fuel
from core.models import Brand, CarModel, Engine, Family, Generation, Variant
from core.provenance import Source, Status
from core.storage import Store
from pipeline.importers import eea
from pipeline.importers.corrections import Corrections, Exclusion, Merge
from pipeline.importers.families import FamilyRules
from pipeline.sources import EEA
from pipeline.validation import validate

TODAY = date(2026, 9, 19)
ROWS = json.loads((Path(__file__).parent / "fixtures" / "eea_sample.json").read_text(encoding="utf-8"))["results"]


def row(**k):
    return {
        "Mk": "FIAT", "Cn": "PANDA", "T": "312", "Va": "A", "Ve": "B", "Ft": "petrol", "Fm": "M",
        "ec": 999, "ep": 52, "m": 1000, "w": None, "at1": None, "co2": 100, "n": 1, **k,
    }


@pytest.fixture
def st():
    with Store() as s:
        yield s


@pytest.fixture
def loaded(st):
    return st, eea.load(ROWS, st, 2025, TODAY)


def test_load_stats(loaded):
    _, s = loaded
    assert s == {"rows": 17, "skipped": 0, "excluded": 0, "conflicts": 0, "brands": 6, "families": 9, "models": 10, "engines": 8, "variants": 14, "dropped": {}}


def test_load_is_valid(loaded):
    st, _ = loaded
    assert validate(st) == []
    assert st.get(Source, "eea-co2") == EEA


def test_most_frequent_values_win(loaded):
    st, _ = loaded
    assert st.get(Variant, "var_fiat-panda-312-pyd1b-s5g").co2_wltp_g_km == 113
    assert st.get(Variant, "var_bmw-x1-xdrive20d-u1x-41eg-fav508l0").co2_wltp_g_km == 130


def test_variant_fields(loaded):
    st, _ = loaded
    v = st.get(Variant, "var_fiat-panda-312-pyd1b-s5g")
    assert (v.name, v.mass_kg, v.year_from, v.year_to) == ("312 PYD1B S5G", 1045, 2025, 2025)
    assert v.wheelbase_mm is None and v.track_width_mm is None
    assert v.generation_id == "gen_fiat-panda-observed"
    assert v.engine_id == "eng_hybrid-999-52"


def test_catalog(loaded):
    st, _ = loaded
    assert st.get(Brand, "brand_fiat").name == "FIAT"
    assert st.get(CarModel, "model_fiat-panda").brand_id == "brand_fiat"
    g = st.get(Generation, "gen_fiat-panda-observed")
    assert (g.name, g.model_id, g.year_from, g.year_to) == ("observed", "model_fiat-panda", 2025, 2025)


def test_engines_and_fuels(loaded):
    st, _ = loaded
    e = st.get(Engine, "eng_hybrid-999-52")
    assert (e.fuel, e.displacement_cc, e.power_kw) == (Fuel.HYBRID, 999, 52)
    assert st.get(Engine, "eng_electric-x-208").displacement_cc is None
    fuels = {e.id: e.fuel for e in st.find(Engine)}
    assert fuels["eng_hydrogen-x-48"] is Fuel.HYDROGEN
    assert fuels["eng_other-2755-151"] is Fuel.OTHER
    assert fuels["eng_phev-1993-145"] is Fuel.PHEV
    assert fuels["eng_lpg-999-74"] is Fuel.LPG


def test_provenance(loaded):
    st, _ = loaded
    ps = {p.field: p for p in st.prov("var_tesla-model-3-003-h6mr-bfb1s5t1w")}
    assert set(ps) == {"mass_kg", "co2_wltp_g_km"}
    p = ps["co2_wltp_g_km"]
    assert p.evidence[0].value == 0
    assert (p.evidence[0].source_id, p.evidence[0].url) == ("eea-co2", eea.PAGE)
    assert p.status is Status.SINGLE and p.last_verified == TODAY
    assert {p.field for p in st.prov("eng_electric-x-208")} == {"power_kw"}


def test_load_default_today(st):
    eea.load([row()], st, 2025)
    assert st.prov("eng_petrol-999-52")[0].last_verified == date.today()


def test_skipped_rows(st):
    s = eea.load([row(Mk=""), row(Mk=None), row(Cn="  "), row(Cn="!!!"), row()], st, 2025, TODAY)
    assert (s["rows"], s["skipped"], s["variants"]) == (5, 4, 1)


def test_spelling_variants_merge(st):
    rs = [row(Mk="FIAT", Cn="PANDA", n=3), row(Mk="Fiat", Cn="Panda", n=1, co2=90)]
    s = eea.load(rs, st, 2025, TODAY)
    assert (s["brands"], s["models"], s["variants"]) == (1, 1, 1)
    m = st.find(CarModel)[0]
    assert (m.name, m.aliases) == ("PANDA", ["Panda"])
    assert st.find(Brand)[0].aliases == ["Fiat"]
    assert st.find(Variant)[0].co2_wltp_g_km == 100


def test_conflicting_engines_keep_majority(st):
    rs = [row(Ft="petrol", Fm="H", ec=1995, ep=110, n=5), row(Ft="diesel", Fm="H", ec=1995, ep=110, n=2)]
    s = eea.load(rs, st, 2025, TODAY)
    assert (s["variants"], s["conflicts"]) == (1, 1)
    assert st.find(Variant)[0].engine_id == "eng_hybrid-1995-110"
    assert validate(st) == []


def test_tie_prefers_lowest_values(st):
    eea.load([row(co2=100, n=1), row(co2=90, n=1), row(co2=None, n=1)], st, 2025, TODAY)
    assert st.find(Variant)[0].co2_wltp_g_km == 90


def test_none_loses_tie(st):
    eea.load([row(co2=None, n=1), row(co2=100, n=1)], st, 2025, TODAY)
    assert st.find(Variant)[0].co2_wltp_g_km == 100


def test_out_of_range_values_dropped(st):
    s = eea.load([row(m=0, co2=5000, ec=-5, ep=0)], st, 2025, TODAY)
    assert s["dropped"] == {"mass_kg": 1, "co2_wltp_g_km": 1, "displacement_cc": 1, "power_kw": 1}
    v = st.find(Variant)[0]
    assert v.mass_kg is None and v.co2_wltp_g_km is None
    assert st.prov(v.id) == []
    e = st.find(Engine)[0]
    assert e.displacement_cc is None and e.power_kw is None
    assert st.prov(e.id) == []


def test_unnamed_variant(st):
    eea.load([row(T=None, Va="", Ve=" ")], st, 2025, TODAY)
    assert st.find(Variant)[0].name == "unknown"


def test_mk_required_fields_still_raise():
    with pytest.raises(ValidationError):
        eea._mk(Engine, Counter(), id="BAD ID", fuel="petrol")


@pytest.mark.parametrize("ft,fm,f", [
    ("petrol", "M", Fuel.PETROL), ("diesel", "M", Fuel.DIESEL), ("lpg", "B", Fuel.LPG),
    ("ng", "M", Fuel.CNG), ("ng-biomethane", "M", Fuel.CNG), ("electric", "E", Fuel.ELECTRIC),
    ("hydrogen", "M", Fuel.HYDROGEN), ("e85", "F", Fuel.OTHER), (None, "M", Fuel.OTHER),
    (" Petrol ", "M", Fuel.PETROL), ("petrol/electric", "P", Fuel.PHEV), ("diesel", "H", Fuel.HYBRID),
])
def test_fuel(ft, fm, f):
    assert eea.fuel(ft, fm) is f


def test_query():
    q = eea.query("co2cars_2025Pv31")
    assert "[latest].[co2cars_2025Pv31]" in q and "MS='IT'" in q and "Ct='M1' AND Cr='M1'" in q
    assert "MS='DE'" in eea.query("t", "DE")


@pytest.mark.parametrize("t,ms", [("x; DROP TABLE y", "IT"), ("", "IT"), ("t", "it"), ("t", "ITA")])
def test_query_rejects_bad_input(t, ms):
    with pytest.raises(ValueError):
        eea.query(t, ms)


def client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch():
    seen = {}

    def h(req):
        seen["q"], seen["ua"] = req.url.params["query"], req.headers["user-agent"]
        return httpx.Response(200, json={"results": ROWS})

    assert eea.fetch("t1", "IT", client(h)) == ROWS
    assert seen["q"] == eea.query("t1", "IT") and seen["ua"] == eea.UA


def test_fetch_api_error():
    with pytest.raises(RuntimeError):
        eea.fetch("t1", client=client(lambda r: httpx.Response(200, json={"errors": [{"error": "x"}]})))


def test_fetch_http_error():
    with pytest.raises(httpx.HTTPStatusError):
        eea.fetch("t1", client=client(lambda r: httpx.Response(500)))


def test_run(tmp_path):
    db = tmp_path / "v.db"
    s = eea.run(db, "t1", 2025, client=client(lambda r: httpx.Response(200, json={"results": ROWS})), today=TODAY)
    assert s["variants"] == 14
    with Store(db, ro=True) as r:
        assert len(r.find(Variant)) == 14


def test_main(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(eea, "run", lambda *a: calls.append(a) or {"ok": 1})
    eea.main(["--table", "t", "--year", "2025", "--db", "x.db"])
    eea.main(["--table", "t", "--year", "2024", "--db", "y.db", "--country", "DE"])
    assert calls == [("x.db", "t", 2025, "IT"), ("y.db", "t", 2024, "DE")]
    assert capsys.readouterr().out.count("{'ok': 1}") == 2


@pytest.mark.parametrize("mk,cn,out", [
    ("FIAT", "FIAT PANDA", "PANDA"),
    ("FIAT", "PANDA", "PANDA"),
    ("FIAT", "FIAT 500 HYBRID", "500 HYBRID"),
    ("ALFA ROMEO", "ALFA ROMEO GIULIA", "GIULIA"),
    ("MERCEDES-BENZ", "MERCEDES-BENZ A 180", "A 180"),
    ("BMW", "BMW", "BMW"),
    ("TESLA", "TESLA", "TESLA"),
    ("FIAT", "FIATTIPO", "FIATTIPO"),
    ("FORD", "FORD-FOCUS", "FORD-FOCUS"),
    ("DS AUTOMOBILES", "DS 3", "DS 3"),
    ("SKODA", "ŠKODA FABIA", "FABIA"),
    ("FIAT", "GRANDE PUNTO", "GRANDE PUNTO"),
])
def test_strip_brand(mk, cn, out):
    assert eea._strip(mk, cn) == out


def test_brand_prefix_merges_models(st):
    rs = [row(Cn="PANDA", Ve="B1", n=5), row(Cn="FIAT PANDA", Ve="B2", n=1), row(Cn="FIAT PANDA", Ve="B1", n=2)]
    s = eea.load(rs, st, 2025, TODAY)
    assert (s["models"], s["variants"]) == (1, 2)
    m = st.find(CarModel)[0]
    assert (m.id, m.name, m.aliases) == ("model_fiat-panda", "PANDA", ["FIAT PANDA"])
    assert [v.id for v in st.find(Variant)] == ["var_fiat-panda-312-a-b1", "var_fiat-panda-312-a-b2"]
    assert {v.generation_id for v in st.find(Variant)} == {"gen_fiat-panda-observed"}


def test_prefixed_only_model_gets_clean_name(st):
    eea.load([row(Cn="FIAT TIPO")], st, 2025, TODAY)
    m = st.find(CarModel)[0]
    assert (m.id, m.name, m.aliases) == ("model_fiat-tipo", "TIPO", ["FIAT TIPO"])


def test_prefixed_names_stay_searchable(st):
    eea.load([row(Cn="FIAT PANDA")], st, 2025, TODAY)
    assert [m.id for m in st.find(CarModel, q="fiat panda")] == ["model_fiat-panda"]
    assert [m.id for m in st.find(CarModel, q="panda")] == ["model_fiat-panda"]


def test_different_names_are_not_merged(st):
    eea.load([row(Cn="PUNTO"), row(Cn="GRANDE PUNTO"), row(Cn="PANDA CROSS"), row(Cn="CROSS PANDA")], st, 2025, TODAY)
    assert sorted(m.name for m in st.find(CarModel)) == ["CROSS PANDA", "GRANDE PUNTO", "PANDA CROSS", "PUNTO"]


def test_registration_counts_from_fixture(loaded):
    st, _ = loaded
    assert st.get(Variant, "var_fiat-panda-312-pyd1b-s5g").registrations == 20519 + 10763
    assert st.get(Variant, "var_fiat-panda-312-pyd1b-c5g").registrations == 15748
    assert st.get(CarModel, "model_fiat-panda").registrations == 15748 + 31282 + 21229 + 8921
    assert st.get(CarModel, "model_tesla-model-3").registrations == 3206 + 1574
    assert st.get(CarModel, "model_toyota-mirai").registrations == 1


def test_model_registrations_are_the_sum_of_its_variants(loaded):
    st, _ = loaded
    for m in st.find(CarModel):
        vs = st.find(Variant, generation_id=f"gen_{m.id[len('model_'):]}-observed")
        assert m.registrations == sum(v.registrations for v in vs) > 0


def test_registrations_ignore_dropped_conflicting_rows(st):
    rs = [row(Ft="petrol", Fm="H", ec=1995, ep=110, n=5), row(Ft="diesel", Fm="H", ec=1995, ep=110, n=2)]
    eea.load(rs, st, 2025, TODAY)
    assert st.find(Variant)[0].registrations == 5
    assert st.find(CarModel)[0].registrations == 5


def test_registrations_add_up_across_spellings(st):
    rs = [row(Cn="PANDA", Ve="B1", n=5), row(Cn="FIAT PANDA", Ve="B2", n=1), row(Cn="FIAT PANDA", Ve="B1", n=2)]
    eea.load(rs, st, 2025, TODAY)
    assert {v.id: v.registrations for v in st.find(Variant)} == {"var_fiat-panda-312-a-b1": 7, "var_fiat-panda-312-a-b2": 1}
    assert st.find(CarModel)[0].registrations == 8


def test_registrations_can_sort_and_filter_imported_models(st):
    eea.load([row(Cn="PANDA", n=100), row(Cn="UNO", n=1), row(Cn="TIPO", n=30)], st, 2025, TODAY)
    assert [m.name for m in st.find(CarModel, sort="-registrations")] == ["PANDA", "TIPO", "UNO"]
    assert [m.name for m in st.find(CarModel, registrations__gte=10, sort="-registrations")] == ["PANDA", "TIPO"]


R = "a long enough reason for the entry"


def test_brand_spellings_merge_into_the_canonical_brand(st):
    rs = [row(Mk="VW", Cn="GOLF", n=2), row(Mk="VOLKSWAGEN", Cn="GOLF", n=10), row(Mk="VOLKSWAGEN, VW", Cn="GOLF", Ve="B2", n=1)]
    s = eea.load(rs, st, 2025, TODAY)
    assert (s["brands"], s["models"], s["variants"]) == (1, 1, 2)
    b = st.find(Brand)[0]
    assert (b.id, b.name, b.aliases) == ("brand_volkswagen", "VOLKSWAGEN", ["VOLKSWAGEN, VW", "VW"])
    assert st.find(CarModel)[0].registrations == 13


def test_canonical_brand_name_is_not_the_alphabetical_first(st):
    eea.load([row(Mk="SSANGJONG", Cn="TORRES")], st, 2025, TODAY)
    b = st.find(Brand)[0]
    assert (b.id, b.name, b.aliases) == ("brand_ssangyong", "SSANGYONG", ["SSANGJONG"])


def test_brand_prefix_is_stripped_with_either_spelling(st):
    rs = [row(Mk="VW", Cn="VW POLO"), row(Mk="VW", Cn="VOLKSWAGEN ID.3"), row(Mk="VOLKSWAGEN", Cn="VOLKSWAGEN UP")]
    eea.load(rs, st, 2025, TODAY)
    assert sorted(m.name for m in st.find(CarModel)) == ["ID.3", "POLO", "UP"]
    assert {m.brand_id for m in st.find(CarModel)} == {"brand_volkswagen"}


def test_reviewed_exclusions_are_applied(st):
    rs = [row(Cn="GOLF"), row(Cn="Golf", Ve="B2"), row(Mk="Fiat", Cn="AVENGER"), row(Cn="PANDA"), row(Mk="JEEP", Cn="AVENGER", n=50)]
    s = eea.load(rs, st, 2025, TODAY)
    assert (s["excluded"], s["skipped"], s["variants"]) == (3, 0, 2)
    assert sorted((m.brand_id, m.name) for m in st.find(CarModel)) == [("brand_fiat", "PANDA"), ("brand_jeep", "AVENGER")]
    assert st.find(Variant, generation_id="gen_fiat-golf-observed") == []


def test_an_excluded_model_does_not_create_its_brand(st):
    s = eea.load([row(Cn="GOLF")], st, 2025, TODAY)
    assert (s["excluded"], s["brands"], s["models"], s["variants"]) == (1, 0, 0, 0)
    assert st.find(Brand) == []


def test_exclusions_use_the_canonical_brand(st):
    c = Corrections(brands={"VW": "VOLKSWAGEN"}, exclude_models=[Exclusion(brand="VOLKSWAGEN", model="POLO", reason=R)])
    s = eea.load([row(Mk="VW", Cn="POLO"), row(Mk="VW", Cn="VW POLO", Ve="B2"), row(Mk="VW", Cn="GOLF")], st, 2025, TODAY, c)
    assert (s["excluded"], s["models"]) == (2, 1)
    assert st.find(CarModel)[0].name == "GOLF"


def test_custom_corrections_replace_the_shipped_ones(st):
    s = eea.load([row(Cn="GOLF"), row(Mk="VW", Cn="POLO")], st, 2025, TODAY, Corrections())
    assert s["excluded"] == 0 and sorted(b.name for b in st.find(Brand)) == ["FIAT", "VW"]


def test_reviewed_merges_join_the_two_spellings_of_a_model(st):
    rs = [
        row(Mk="TOYOTA", Cn="GR YARIS", Ve="B1", n=83),
        row(Mk="TOYOTA", Cn="YARIS GR", Ve="B2", n=7),
        row(Mk="TOYOTA", Cn="TOYOTA YARIS GR", Ve="B3", n=2),
    ]
    s = eea.load(rs, st, 2025, TODAY)
    assert (s["models"], s["variants"]) == (1, 3)
    m = st.find(CarModel)[0]
    assert (m.id, m.name, m.registrations) == ("model_toyota-gr-yaris", "GR YARIS", 92)
    assert m.aliases == ["TOYOTA YARIS GR", "YARIS GR"]
    assert {v.generation_id for v in st.find(Variant)} == {"gen_toyota-gr-yaris-observed"}


def test_reviewed_merge_of_the_fiat_abarth_500(st):
    eea.load([row(Cn="ABARTH 500", Ve="B1", n=85), row(Cn="500 ABARTH", Ve="B2", n=1)], st, 2025, TODAY)
    m = st.find(CarModel)[0]
    assert (m.name, m.aliases, m.registrations) == ("ABARTH 500", ["500 ABARTH"], 86)


def test_a_merged_model_alone_gets_the_canonical_name(st):
    eea.load([row(Mk="TOYOTA", Cn="YARIS GR", n=7)], st, 2025, TODAY)
    m = st.find(CarModel)[0]
    assert (m.id, m.name, m.aliases) == ("model_toyota-gr-yaris", "GR YARIS", ["YARIS GR"])


def test_merged_spellings_of_the_same_version_become_one_variant(st):
    eea.load([row(Mk="TOYOTA", Cn="GR YARIS", n=3), row(Mk="TOYOTA", Cn="YARIS GR", n=4)], st, 2025, TODAY)
    v = st.find(Variant)
    assert len(v) == 1 and v[0].registrations == 7


def test_merges_only_apply_to_their_own_brand(st):
    eea.load([row(Mk="FIAT", Cn="YARIS GR"), row(Mk="TOYOTA", Cn="YARIS GR")], st, 2025, TODAY)
    assert sorted((m.brand_id, m.name) for m in st.find(CarModel)) == [("brand_fiat", "YARIS GR"), ("brand_toyota", "GR YARIS")]


def test_no_merge_without_the_correction(st):
    eea.load([row(Mk="TOYOTA", Cn="GR YARIS"), row(Mk="TOYOTA", Cn="YARIS GR")], st, 2025, TODAY, Corrections())
    assert sorted(m.name for m in st.find(CarModel)) == ["GR YARIS", "YARIS GR"]


def test_custom_merge_uses_the_canonical_brand_and_the_cleaned_name(st):
    c = Corrections(brands={"VW": "VOLKSWAGEN"}, merge_models=[Merge(brand="VOLKSWAGEN", model="GOLF GTI", into="GOLF", reason=R)])
    eea.load([row(Mk="VW", Cn="VW GOLF GTI", n=2), row(Mk="VOLKSWAGEN", Cn="GOLF", Ve="B2", n=10)], st, 2025, TODAY, c)
    m = st.find(CarModel)[0]
    assert (m.id, m.name, m.registrations) == ("model_volkswagen-golf", "GOLF", 12)
    assert "GOLF GTI" in m.aliases and "VW GOLF GTI" in m.aliases



def test_every_model_has_a_family_of_its_own_brand(loaded):
    st, _ = loaded
    for m in st.find(CarModel):
        f = st.get(Family, m.family_id)
        assert f is not None and f.brand_id == m.brand_id


def test_a_brand_without_rules_has_one_family_per_model(loaded):
    st, _ = loaded
    f = st.get(Family, "family_fiat-panda")
    assert (f.name, f.brand_id, f.model_count, f.registrations) == ("PANDA", "brand_fiat", 1, 77180)
    assert st.get(CarModel, "model_fiat-panda").family_id == "family_fiat-panda"
    assert (len(st.find(Family)), len(st.find(CarModel))) == (9, 10)


def test_family_totals_match_their_models(loaded):
    st, _ = loaded
    for f in st.find(Family):
        ms = st.find(CarModel, family_id=f.id)
        assert f.model_count == len(ms) and f.registrations == sum(m.registrations for m in ms)
    assert sum(f.registrations for f in st.find(Family)) == sum(m.registrations for m in st.find(CarModel))


def test_family_ids_use_the_canonical_brand_and_model_name(st):
    eea.load([row(Mk="VW", Cn="VW GOLF", n=2), row(Mk="VOLKSWAGEN", Cn="GOLF", Ve="B2", n=10), row(Cn="FIAT PANDA")], st, 2025, TODAY)
    assert sorted(f.id for f in st.find(Family)) == ["family_fiat-panda", "family_volkswagen-golf"]
    f = st.get(Family, "family_volkswagen-golf")
    assert (f.name, f.model_count, f.registrations) == ("GOLF", 1, 12)


def test_families_are_stored_before_their_models_and_reload_from_disk(tmp_path):
    db = tmp_path / "f.db"
    with Store(db) as s:
        eea.load(ROWS, s, 2025, TODAY)
    with Store(db, ro=True) as r:
        assert len(r.find(Family)) == 9 and all(m.family_id for m in r.find(CarModel))


def test_rules_group_models_into_families(loaded):
    st, _ = loaded
    x1 = st.get(Family, "family_bmw-x1")
    assert (x1.name, x1.brand_id, x1.model_count, x1.registrations) == ("X1", "brand_bmw", 2, 548 + 400 + 174)
    assert {m.id for m in st.find(CarModel, family_id="family_bmw-x1")} == {"model_bmw-x1-xdrive20d", "model_bmw-x1-sdrive20d"}
    assert st.get(Family, "family_bmw-x2").registrations == 1087
    glc = st.get(Family, "family_mercedes-benz-glc")
    assert (glc.name, glc.model_count, glc.registrations) == ("GLC", 1, 461)


def test_the_family_totals_add_up_with_rules(loaded):
    st, _ = loaded
    assert sum(f.model_count for f in st.find(Family)) == len(st.find(CarModel))
    assert sum(f.registrations for f in st.find(Family)) == sum(m.registrations for m in st.find(CarModel))
    assert validate(st) == []


def test_models_of_related_but_different_cars_stay_in_separate_families(st):
    eea.load([row(Mk="TOYOTA", Cn="YARIS", n=5), row(Mk="TOYOTA", Cn="YARIS CROSS", Ve="B2", n=9)], st, 2025, TODAY)
    assert sorted(f.name for f in st.find(Family)) == ["YARIS", "YARIS CROSS"]


def test_custom_rules_replace_the_shipped_ones(st):
    rows = [row(Mk="BMW", Cn="X1 SDRIVE18D", n=3), row(Mk="BMW", Cn="X1 XDRIVE20D", Ve="B2", n=4)]
    eea.load(rows, st, 2025, TODAY, None, FamilyRules())
    assert sorted(f.name for f in st.find(Family)) == ["X1 SDRIVE18D", "X1 XDRIVE20D"]


def test_the_family_uses_the_canonical_brand_for_its_rules(st):
    eea.load([row(Mk="MERCEDES", Cn="MERCEDES GLC 220 D", n=2), row(Mk="MERCEDES-BENZ", Cn="GLC 300 E", Ve="B2", n=8)], st, 2025, TODAY)
    f = st.find(Family)[0]
    assert (f.id, f.name, f.model_count, f.registrations) == ("family_mercedes-benz-glc", "GLC", 2, 10)


def test_a_family_can_hold_a_model_named_like_it(st):
    rows = [row(Mk="PORSCHE", Cn="MACAN", n=4), row(Mk="PORSCHE", Cn="MACAN 4S", Ve="B2", n=6)]
    eea.load(rows, st, 2025, TODAY)
    f = st.find(Family)[0]
    assert (f.id, f.model_count, f.registrations) == ("family_porsche-macan", 2, 10)
