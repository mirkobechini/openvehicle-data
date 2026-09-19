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
    assert j["counts"] == {"Brand": 6, "CarModel": 10, "Generation": 10, "Engine": 8, "Variant": 14, "Source": 1}
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
    assert n(model_id="nope") == 0
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
