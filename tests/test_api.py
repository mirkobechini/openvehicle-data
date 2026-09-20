import json
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.storage import Store
from pipeline.importers import eea
from service.app import create_app

ROWS = json.loads((Path(__file__).parent / "fixtures" / "eea_sample.json").read_text(encoding="utf-8"))["results"]
B = "/api/v1"
PANDA = "var_fiat-panda-312-pyd1b-s5g"


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    p = tmp_path_factory.mktemp("api") / "v.db"
    with Store(p) as st:
        eea.load(ROWS, st, 2025, date(2026, 9, 19))
    return p


@pytest.fixture(scope="module")
def cl(db):
    return TestClient(create_app(db))


def ids(r):
    return [i["id"] for i in r.json()["items"]]


def test_missing_db(tmp_path):
    with pytest.raises(FileNotFoundError):
        create_app(tmp_path / "none.db")


def test_env_and_default_db(db, tmp_path, monkeypatch):
    monkeypatch.setenv("OVD_DB", str(db))
    assert TestClient(create_app()).get(f"{B}/health").status_code == 200
    monkeypatch.delenv("OVD_DB")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(FileNotFoundError):
        create_app()
    (tmp_path / "openvehicle-data.db").write_bytes(db.read_bytes())
    assert TestClient(create_app()).get(f"{B}/health").status_code == 200


def test_health(cl):
    r = cl.get(f"{B}/health")
    assert (r.status_code, r.json()) == (200, {"status": "ok"})


def test_meta(cl):
    j = cl.get(f"{B}/meta").json()
    assert j["counts"] == {"Brand": 6, "Family": 9, "CarModel": 10, "Generation": 10, "Engine": 8, "Variant": 14, "Source": 1}
    assert j["license"] == "CC-BY-4.0" and "CC BY 4.0" in j["attribution"] and j["version"]
    assert j["sources"][0]["id"] == "eea-co2"


def test_brands(cl):
    r = cl.get(f"{B}/brands")
    assert r.status_code == 200
    j = r.json()
    assert (j["total"], j["limit"], j["offset"]) == (6, 50, 0)
    assert ids(r) == sorted(ids(r)) and "brand_fiat" in ids(r)


def test_brands_paging_and_search(cl):
    assert len(cl.get(f"{B}/brands", params={"limit": 2}).json()["items"]) == 2
    r = cl.get(f"{B}/brands", params={"limit": 2, "offset": 4})
    assert r.json()["total"] == 6 and len(r.json()["items"]) == 2
    r = cl.get(f"{B}/brands", params={"q": "FIA"})
    assert ids(r) == ["brand_fiat"] and r.json()["total"] == 1
    assert cl.get(f"{B}/brands", params={"q": "%"}).json()["total"] == 0


@pytest.mark.parametrize("p", [{"limit": 0}, {"limit": 201}, {"offset": -1}, {"q": ""}, {"limit": "x"}])
def test_bad_parameters(cl, p):
    assert cl.get(f"{B}/brands", params=p).status_code == 422


def test_brand_detail(cl):
    r = cl.get(f"{B}/brands/brand_fiat")
    assert (r.status_code, r.json()["name"]) == (200, "FIAT")
    r = cl.get(f"{B}/brands/nope")
    assert (r.status_code, r.json()["detail"]) == (404, "Brand nope not found")


def test_models(cl):
    assert cl.get(f"{B}/models").json()["total"] == 10
    assert ids(cl.get(f"{B}/models", params={"brand_id": "brand_tesla"})) == ["model_tesla-model-3", "model_tesla-model-y"]
    assert ids(cl.get(f"{B}/models", params={"q": "panda"})) == ["model_fiat-panda"]
    assert cl.get(f"{B}/models", params={"brand_id": "brand_tesla", "q": "y"}).json()["total"] == 1


def test_model_detail(cl):
    assert cl.get(f"{B}/models/model_fiat-panda").json()["brand_id"] == "brand_fiat"
    assert cl.get(f"{B}/models/nope").status_code == 404


def test_generations(cl):
    assert cl.get(f"{B}/generations").json()["total"] == 10
    r = cl.get(f"{B}/generations", params={"model_id": "model_fiat-panda"})
    assert ids(r) == ["gen_fiat-panda-observed"]


def test_engines(cl):
    assert cl.get(f"{B}/engines").json()["total"] == 8
    assert cl.get(f"{B}/engines", params={"fuel": "phev"}).json()["total"] == 1
    assert cl.get(f"{B}/engines", params={"fuel": "steam"}).status_code == 422
    assert cl.get(f"{B}/engines/eng_hybrid-999-52").json()["power_kw"] == 52
    assert cl.get(f"{B}/engines/nope").status_code == 404


def test_variants_all_and_search(cl):
    assert cl.get(f"{B}/variants").json()["total"] == 14
    assert ids(cl.get(f"{B}/variants", params={"q": "s5g"})) == [PANDA]


def test_variants_filters(cl):
    def n(**p):
        return cl.get(f"{B}/variants", params=p).json()["total"]
    assert n(model_id="model_fiat-panda") == 4
    assert n(generation_id="gen_fiat-panda-observed") == 4
    assert n(model_id="model_fiat-panda", generation_id="gen_fiat-panda-observed") == 4
    assert n(model_id="model_fiat-panda", generation_id="gen_tesla-model-3-observed") == 0
    assert n(fuel="electric") == 3
    assert n(engine_id="eng_electric-x-208") == 2
    assert n(fuel="electric", engine_id="eng_electric-x-208") == 2
    assert n(fuel="electric", engine_id="eng_hybrid-999-52") == 0
    assert n(fuel="electric", model_id="model_fiat-panda") == 0
    assert n(fuel="hybrid", model_id="model_fiat-panda", q="c5") == 2


def test_variant_detail(cl):
    j = cl.get(f"{B}/variants/{PANDA}").json()
    assert (j["id"], j["mass_kg"], j["engine"]["id"]) == (PANDA, 1045, "eng_hybrid-999-52")
    assert {(p["entity_id"], p["field"]) for p in j["provenance"]} == {
        (PANDA, "mass_kg"), (PANDA, "co2_wltp_g_km"),
        ("eng_hybrid-999-52", "displacement_cc"), ("eng_hybrid-999-52", "power_kw"),
    }
    assert {p["status"] for p in j["provenance"]} == {"single_source"}
    assert cl.get(f"{B}/variants/nope").status_code == 404


def test_sources(cl):
    j = cl.get(f"{B}/sources").json()
    assert [s["id"] for s in j] == ["eea-co2"] and j[0]["license"] == "CC-BY-4.0"


def test_search(cl):
    j = cl.get(f"{B}/search", params={"q": "fiat"}).json()
    assert [b["id"] for b in j["brands"]] == ["brand_fiat"] and j["models"] == []
    j = cl.get(f"{B}/search", params={"q": "panda"}).json()
    assert j["brands"] == [] and [m["id"] for m in j["models"]] == ["model_fiat-panda"]
    assert cl.get(f"{B}/search").status_code == 422
    assert cl.get(f"{B}/search", params={"q": ""}).status_code == 422


def test_search_is_limited_to_ten(tmp_path):
    from core.models import Brand
    p = tmp_path / "m.db"
    with Store(p) as st:
        st.put(*(Brand(id=f"brand_b{i}", name=f"Brand {i}") for i in range(12)))
    assert len(TestClient(create_app(p)).get(f"{B}/search", params={"q": "brand"}).json()["brands"]) == 10


def test_read_only_and_cors(cl):
    assert cl.post(f"{B}/brands").status_code == 405
    assert cl.delete(f"{B}/brands/brand_fiat").status_code == 405
    r = cl.get(f"{B}/health", headers={"Origin": "https://example.org"})
    assert r.headers["access-control-allow-origin"] == "*"


def test_openapi(cl):
    j = cl.get("/openapi.json").json()
    assert j["info"]["title"] == "openvehicle-data"
    assert {f"{B}/variants", f"{B}/variants/{{i}}", f"{B}/search", f"{B}/meta"} <= set(j["paths"])
    assert all(list(v) == ["get"] for v in j["paths"].values())


def test_models_sorted_by_popularity(cl):
    r = cl.get(f"{B}/models", params={"sort": "registrations"})
    assert ids(r)[:3] == ["model_fiat-panda", "model_dacia-sandero", "model_tesla-model-3"]
    assert r.json()["items"][0]["registrations"] == 77180
    assert ids(cl.get(f"{B}/models"))[0] != "model_fiat-panda"


def test_models_minimum_registrations(cl):
    r = cl.get(f"{B}/models", params={"min_registrations": 5000, "sort": "registrations"})
    assert ids(r) == ["model_fiat-panda", "model_dacia-sandero"] and r.json()["total"] == 2
    assert cl.get(f"{B}/models", params={"min_registrations": 0}).json()["total"] == 10
    assert cl.get(f"{B}/models", params={"min_registrations": 10**9}).json()["total"] == 0


def test_models_popularity_with_other_filters(cl):
    r = cl.get(f"{B}/models", params={"brand_id": "brand_tesla", "sort": "registrations", "min_registrations": 2000})
    assert ids(r) == ["model_tesla-model-3"]
    r = cl.get(f"{B}/models", params={"sort": "registrations", "limit": 1, "offset": 1})
    assert ids(r) == ["model_dacia-sandero"] and r.json()["total"] == 10


def test_variants_sorted_by_popularity(cl):
    r = cl.get(f"{B}/variants", params={"sort": "registrations", "limit": 2})
    assert ids(r) == ["var_fiat-panda-312-pyd1b-s5g", "var_fiat-panda-312-pyd1b-s4g"]
    assert r.json()["items"][0]["registrations"] == 31282


def test_variants_minimum_registrations_and_filters(cl):
    r = cl.get(f"{B}/variants", params={"min_registrations": 20000, "sort": "registrations"})
    assert ids(r) == ["var_fiat-panda-312-pyd1b-s5g", "var_fiat-panda-312-pyd1b-s4g"]
    r = cl.get(f"{B}/variants", params={"fuel": "electric", "min_registrations": 3000})
    assert ids(r) == ["var_tesla-model-3-003-h6mr-bfb1s5t1w"]


@pytest.mark.parametrize("path,p", [
    ("models", {"sort": "popular"}), ("models", {"min_registrations": -1}), ("models", {"min_registrations": "x"}),
    ("variants", {"sort": "name"}), ("variants", {"min_registrations": -5}),
])
def test_popularity_bad_parameters(cl, path, p):
    assert cl.get(f"{B}/{path}", params=p).status_code == 422


def test_registrations_are_documented(cl):
    j = cl.get("/openapi.json").json()["paths"][f"{B}/models"]["get"]["parameters"]
    assert {"sort", "min_registrations"} <= {x["name"] for x in j}


def test_openapi_declares_provenance_status(cl):
    entry = cl.get("/openapi.json").json()["components"]["schemas"]["ProvenanceOut"]
    assert "status" in entry["properties"] and "status" in entry["required"]
    j = cl.get(f"{B}/variants/{PANDA}").json()
    assert {p["status"] for p in j["provenance"]} == {"single_source"}


def test_page_metadata_middle_and_last_page(cl):
    j = cl.get(f"{B}/brands", params={"limit": 4}).json()
    assert (j["total"], j["count"], j["has_more"], j["next_offset"]) == (6, 4, True, 4)
    j = cl.get(f"{B}/brands", params={"limit": 4, "offset": 4}).json()
    assert (j["total"], j["count"], j["has_more"], j["next_offset"]) == (6, 2, False, None)


def test_page_metadata_complete_and_empty_lists(cl):
    j = cl.get(f"{B}/brands").json()
    assert (j["count"], j["has_more"], j["next_offset"]) == (6, False, None)
    j = cl.get(f"{B}/brands", params={"q": "zzzz"}).json()
    assert (j["total"], j["count"], j["has_more"], j["next_offset"]) == (0, 0, False, None)


def test_page_metadata_past_the_end(cl):
    j = cl.get(f"{B}/brands", params={"offset": 50}).json()
    assert (j["total"], j["count"], j["has_more"], j["next_offset"], j["items"]) == (6, 0, False, None, [])


def test_page_metadata_exact_multiple_of_the_limit(cl):
    j = cl.get(f"{B}/brands", params={"limit": 3, "offset": 3}).json()
    assert (j["count"], j["has_more"], j["next_offset"]) == (3, False, None)


def test_paging_through_everything_with_next_offset(cl):
    seen, off = [], 0
    while off is not None:
        j = cl.get(f"{B}/variants", params={"limit": 4, "offset": off}).json()
        assert j["count"] == len(j["items"])
        seen += [i["id"] for i in j["items"]]
        off = j["next_offset"]
    assert len(seen) == 14 and len(set(seen)) == 14


@pytest.mark.parametrize("path", ["brands", "models", "generations", "engines", "variants"])
def test_every_paged_list_has_the_metadata(cl, path):
    j = cl.get(f"{B}/{path}", params={"limit": 1}).json()
    assert {"total", "limit", "offset", "count", "has_more", "next_offset", "items"} <= set(j)
    assert j["count"] == 1 and j["has_more"] is True and j["next_offset"] == 1


def test_variants_by_brand(cl):
    r = cl.get(f"{B}/variants", params={"brand_id": "brand_tesla"})
    assert r.json()["total"] == 3 and all("tesla" in i for i in ids(r))
    assert cl.get(f"{B}/variants", params={"brand_id": "brand_fiat"}).json()["total"] == 4
    assert cl.get(f"{B}/variants", params={"brand_id": "brand_bmw"}).json()["total"] == 3


def test_variants_by_brand_combined_with_other_filters(cl):
    def n(**p):
        return cl.get(f"{B}/variants", params=p).json()["total"]
    assert n(brand_id="brand_tesla", fuel="electric") == 3
    assert n(brand_id="brand_fiat", fuel="electric") == 0
    assert n(brand_id="brand_tesla", model_id="model_tesla-model-3") == 2
    assert n(brand_id="brand_fiat", model_id="model_tesla-model-3") == 0
    assert n(brand_id="brand_tesla", generation_id="gen_tesla-model-y-observed") == 1
    assert n(brand_id="brand_tesla", engine_id="eng_electric-x-208") == 2
    assert n(brand_id="brand_tesla", min_registrations=1500) == 2
    assert n(brand_id="brand_tesla", min_registrations=2000) == 1
    assert n(brand_id="brand_fiat", q="s5g") == 1


def test_variants_by_brand_sorted_and_paged(cl):
    r = cl.get(f"{B}/variants", params={"brand_id": "brand_tesla", "sort": "registrations", "limit": 1})
    assert ids(r) == ["var_tesla-model-3-003-h6mr-bfb1s5t1w"]
    assert (r.json()["total"], r.json()["has_more"], r.json()["next_offset"]) == (3, True, 1)


def test_variants_of_a_real_brand_with_no_match_are_an_empty_list(cl):
    r = cl.get(f"{B}/variants", params={"brand_id": "brand_fiat", "fuel": "electric"})
    assert (r.status_code, r.json()["total"], r.json()["items"]) == (200, 0, [])


def test_variants_brand_filter_is_documented(cl):
    j = cl.get("/openapi.json").json()["paths"][f"{B}/variants"]["get"]["parameters"]
    assert "brand_id" in {x["name"] for x in j}


UNKNOWN = [
    ("models", {"brand_id": "brand_teslaa"}, "Brand", "brand_teslaa", "brand_tesla"),
    ("generations", {"model_id": "model_fiat-pandaa"}, "CarModel", "model_fiat-pandaa", "model_fiat-panda"),
    ("variants", {"brand_id": "brand_bmww"}, "Brand", "brand_bmww", "brand_bmw"),
    ("variants", {"model_id": "model_fiat-pandaa"}, "CarModel", "model_fiat-pandaa", "model_fiat-panda"),
    ("variants", {"generation_id": "gen_fiat-panda-observedd"}, "Generation", "gen_fiat-panda-observedd", "gen_fiat-panda-observed"),
    ("variants", {"engine_id": "eng_hybrid-999-522"}, "Engine", "eng_hybrid-999-522", "eng_hybrid-999-52"),
]


@pytest.mark.parametrize("path,p,cls,bad,good", UNKNOWN)
def test_unknown_filter_id_is_a_404_with_a_suggestion(cl, path, p, cls, bad, good):
    r = cl.get(f"{B}/{path}", params=p)
    d = r.json()["detail"]
    assert r.status_code == 404 and d.startswith(f"{cls} {bad} not found. Did you mean: ") and good in d


@pytest.mark.parametrize("path,p,cls,bad", [("models", {"brand_id": "zzzzzz"}, "Brand", "zzzzzz"), ("variants", {"engine_id": "zzzzzz"}, "Engine", "zzzzzz")])
def test_unknown_filter_id_without_a_close_match_has_no_suggestion(cl, path, p, cls, bad):
    r = cl.get(f"{B}/{path}", params=p)
    assert (r.status_code, r.json()["detail"]) == (404, f"{cls} {bad} not found")


def test_suggestions_ignore_case(cl):
    r = cl.get(f"{B}/models", params={"brand_id": "BRAND_FIAT"})
    assert r.status_code == 404 and "brand_fiat" in r.json()["detail"]


def test_an_empty_filter_value_is_ignored(cl):
    assert cl.get(f"{B}/models", params={"brand_id": ""}).json()["total"] == 10


def test_valid_filter_ids_still_work(cl):
    assert cl.get(f"{B}/models", params={"brand_id": "brand_fiat"}).status_code == 200
    assert cl.get(f"{B}/generations", params={"model_id": "model_fiat-panda"}).json()["total"] == 1
    r = cl.get(f"{B}/variants", params={"brand_id": "brand_fiat", "model_id": "model_fiat-panda", "generation_id": "gen_fiat-panda-observed", "engine_id": "eng_hybrid-999-52"})
    assert r.status_code == 200 and r.json()["total"] == 4


@pytest.mark.parametrize("path,bad,good", [
    ("brands", "brand_fiatt", "brand_fiat"),
    ("models", "model_fiat-pandaa", "model_fiat-panda"),
    ("engines", "eng_hybrid-999-5", "eng_hybrid-999-52"),
    ("variants", "var_fiat-panda-312-pyd1b-s5", "var_fiat-panda-312-pyd1b-s5g"),
])
def test_detail_of_an_unknown_id_suggests_close_ids(cl, path, bad, good):
    r = cl.get(f"{B}/{path}/{bad}")
    assert r.status_code == 404 and "Did you mean: " in r.json()["detail"] and good in r.json()["detail"]


def test_at_most_three_suggestions(cl):
    d = cl.get(f"{B}/variants/var_fiat-panda-312-pyd1b-s").json()["detail"]
    assert len(d.split("Did you mean: ")[1].rstrip("?").split(", ")) <= 3


@pytest.mark.parametrize("q,name", [("teslaa", "TESLA"), ("Tesal", "TESLA"), ("fiatt", "FIAT"), ("toyta", "TOYOTA")])
def test_search_suggests_close_names_when_nothing_is_found(cl, q, name):
    j = cl.get(f"{B}/search", params={"q": q}).json()
    assert (j["brands"], j["models"]) == ([], []) and name in j["did_you_mean"] and len(j["did_you_mean"]) <= 5


def test_search_without_a_close_name_has_no_suggestions(cl):
    j = cl.get(f"{B}/search", params={"q": "zzzzzz"}).json()
    assert (j["brands"], j["models"], j["did_you_mean"]) == ([], [], [])


def test_search_with_results_has_no_suggestions(cl):
    j = cl.get(f"{B}/search", params={"q": "tesla"}).json()
    assert j["brands"] and j["did_you_mean"] == []
    assert cl.get(f"{B}/search", params={"q": "model 3"}).json()["did_you_mean"] == []


def test_search_can_suggest_a_model_alias(cl):
    assert "PANDA" in cl.get(f"{B}/search", params={"q": "pandaa"}).json()["did_you_mean"]


FAMS = [
    "family_fiat-panda", "family_dacia-sandero", "family_tesla-model-3", "family_tesla-model-y", "family_bmw-x1",
    "family_bmw-x2", "family_mercedes-benz-glc", "family_toyota-land-cruiser", "family_toyota-mirai",
]


def test_families_list(cl):
    r = cl.get(f"{B}/families")
    j = r.json()
    assert (r.status_code, j["total"], j["count"]) == (200, 9, 9) and ids(r) == sorted(FAMS)
    assert {"id", "brand_id", "name", "aliases", "model_count", "registrations"} <= set(j["items"][0])


def test_families_sorted_by_registrations(cl):
    r = cl.get(f"{B}/families", params={"sort": "registrations"})
    assert ids(r) == FAMS
    assert r.json()["items"][0]["registrations"] == 77180


def test_families_filters(cl):
    assert ids(cl.get(f"{B}/families", params={"brand_id": "brand_bmw", "sort": "registrations"})) == ["family_bmw-x1", "family_bmw-x2"]
    assert ids(cl.get(f"{B}/families", params={"min_registrations": 1000, "sort": "registrations"})) == FAMS[:6]
    assert ids(cl.get(f"{B}/families", params={"q": "x1"})) == ["family_bmw-x1"]
    assert cl.get(f"{B}/families", params={"brand_id": "brand_bmw", "min_registrations": 1100}).json()["total"] == 1


def test_families_paging_metadata(cl):
    j = cl.get(f"{B}/families", params={"limit": 4}).json()
    assert (j["total"], j["count"], j["has_more"], j["next_offset"]) == (9, 4, True, 4)


def test_family_detail_and_typos(cl):
    j = cl.get(f"{B}/families/family_bmw-x1").json()
    assert (j["name"], j["brand_id"], j["model_count"], j["registrations"]) == ("X1", "brand_bmw", 2, 548 + 400 + 174)
    r = cl.get(f"{B}/families/family_bmw-x11")
    assert r.status_code == 404 and "Did you mean: " in r.json()["detail"] and "family_bmw-x1" in r.json()["detail"]
    r = cl.get(f"{B}/families", params={"brand_id": "brand_bmww"})
    assert r.status_code == 404 and "brand_bmw" in r.json()["detail"]


def test_models_of_a_family(cl):
    r = cl.get(f"{B}/models", params={"family_id": "family_bmw-x1"})
    assert sorted(ids(r)) == ["model_bmw-x1-sdrive20d", "model_bmw-x1-xdrive20d"] and r.json()["total"] == 2
    assert all(i["family_id"] == "family_bmw-x1" for i in r.json()["items"])
    assert cl.get(f"{B}/models", params={"family_id": "family_bmw-x1", "brand_id": "brand_fiat"}).json()["total"] == 0
    assert cl.get(f"{B}/models", params={"family_id": "family_bmw-x1", "q": "sdrive"}).json()["total"] == 1


def test_variants_of_a_family(cl):
    def n(**p):
        return cl.get(f"{B}/variants", params=p).json()["total"]
    assert n(family_id="family_bmw-x1") == 2 and n(family_id="family_bmw-x2") == 1
    assert n(family_id="family_bmw-x1", brand_id="brand_bmw") == 2 and n(family_id="family_bmw-x1", brand_id="brand_fiat") == 0
    assert n(family_id="family_bmw-x1", fuel="hybrid") == 2 and n(family_id="family_bmw-x1", fuel="electric") == 0
    assert n(family_id="family_bmw-x1", model_id="model_bmw-x1-sdrive20d") == 1
    assert n(family_id="family_bmw-x1", model_id="model_bmw-x2-xdrive20d") == 0


def test_unknown_family_filters_are_404_with_suggestions(cl):
    for path in ("models", "variants"):
        r = cl.get(f"{B}/{path}", params={"family_id": "family_bmw-x11"})
        assert r.status_code == 404 and "Did you mean: " in r.json()["detail"] and "family_bmw-x1" in r.json()["detail"]


def test_search_finds_families(cl):
    j = cl.get(f"{B}/search", params={"q": "x1"}).json()
    assert [f["id"] for f in j["families"]] == ["family_bmw-x1"] and j["did_you_mean"] == []
    assert cl.get(f"{B}/search", params={"q": "glc"}).json()["families"][0]["id"] == "family_mercedes-benz-glc"
    assert cl.get(f"{B}/search", params={"q": "zzzzzz"}).json()["families"] == []


def test_search_suggests_family_names(cl):
    j = cl.get(f"{B}/search", params={"q": "glcc"}).json()
    assert (j["brands"], j["families"], j["models"]) == ([], [], []) and "GLC" in j["did_you_mean"]


def test_families_are_in_the_openapi(cl):
    paths = cl.get("/openapi.json").json()["paths"]
    assert {f"{B}/families", f"{B}/families/{{i}}"} <= set(paths)
    for p in ("models", "variants"):
        assert "family_id" in {x["name"] for x in paths[f"{B}/{p}"]["get"]["parameters"]}


def test_variants_by_year(cl):
    a = cl.get(f"{B}/variants").json()["total"]
    assert cl.get(f"{B}/variants", params={"year": 2025}).json()["total"] == a
    assert cl.get(f"{B}/variants", params={"year": 2019}).json()["total"] == 0
    assert cl.get(f"{B}/variants", params={"year": 1800}).status_code == 422


def test_search_text_is_capped(cl):
    assert cl.get(f"{B}/models", params={"q": "a" * 100}).status_code == 200
    assert cl.get(f"{B}/models", params={"q": "a" * 101}).status_code == 422
    assert cl.get(f"{B}/search", params={"q": "a" * 101}).status_code == 422


def test_meta_says_unknown_for_a_dataset_without_a_version(cl):
    j = cl.get(f"{B}/meta").json()
    assert j["version"] == "unknown" and j["generated"] is None and j["software_version"]


def test_meta_reports_the_data_version(db, tmp_path):
    import shutil

    p = tmp_path / "v.db"
    shutil.copy(db, p)
    with Store(p) as s:
        s.set_meta("version", "0.7.0")
        s.set_meta("generated", "2026-09-20")
    j = TestClient(create_app(p)).get(f"{B}/meta").json()
    assert (j["version"], j["generated"]) == ("0.7.0", "2026-09-20")
