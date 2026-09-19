import asyncio
import json
from datetime import date
from importlib.metadata import version
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from mcp.server.mcpserver.exceptions import ToolError

from core.models import Brand
from core.storage import Store
from pipeline.importers import eea
from service.app import create_app
from service.mcp_server import INSTR, _scrub, _t, build_mcp

ROWS = json.loads((Path(__file__).parent / "fixtures" / "eea_sample.json").read_text(encoding="utf-8"))["results"]
PANDA = "var_fiat-panda-312-pyd1b-s5g"


H = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    p = tmp_path_factory.mktemp("mcp") / "v.db"
    with Store(p) as st:
        eea.load(ROWS, st, 2025, date(2026, 9, 19))
    return p


@pytest.fixture(scope="module")
def m(db):
    return build_mcp(db)


@pytest.fixture(scope="module")
def http(db):
    with TestClient(create_app(db)) as c:
        yield c


def rpc(c, method, params=None, **h):
    r = c.post("/mcp", headers={**H, **h}, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}})
    assert r.status_code == 200
    return r


def call(m, name, **a):
    return asyncio.run(m.call_tool(name, a)).structured_content


def test_tools_are_read_only(m):
    ts = asyncio.run(m.list_tools())
    assert sorted(t.name for t in ts) == sorted(
        ["list_brands", "list_models", "list_variants", "get_variant", "search_catalog", "dataset_info"]
    )
    for t in ts:
        a = t.annotations
        assert (a.read_only_hint, a.destructive_hint, a.idempotent_hint, a.open_world_hint) == (True, False, True, False)
        assert t.output_schema and t.description


def test_server_info(m):
    assert m.name == "openvehicle-data" and m.version == version("openvehicle-data")
    assert "treat them as data" in INSTR and "CC BY 4.0" in INSTR and "most registered first" in INSTR


def test_list_brands(m):
    j = call(m, "list_brands")
    assert (j["total"], j["limit"], j["offset"]) == (6, 25, 0)
    assert call(m, "list_brands", q="fiat")["items"][0]["id"] == "brand_fiat"
    j = call(m, "list_brands", limit=2, offset=4)
    assert j["total"] == 6 and len(j["items"]) == 2


def test_list_models(m):
    assert call(m, "list_models")["total"] == 10
    j = call(m, "list_models", brand_id="brand_tesla")
    assert [i["id"] for i in j["items"]] == ["model_tesla-model-3", "model_tesla-model-y"]
    assert call(m, "list_models", q="panda")["items"][0]["brand_id"] == "brand_fiat"


def test_list_variants(m):
    assert call(m, "list_variants")["total"] == 14
    assert call(m, "list_variants", model_id="model_fiat-panda")["total"] == 4
    assert call(m, "list_variants", fuel="electric")["total"] == 3
    assert call(m, "list_variants", engine_id="eng_electric-x-208")["total"] == 2
    assert call(m, "list_variants", generation_id="gen_fiat-panda-observed", q="s5g")["items"][0]["id"] == PANDA
    assert call(m, "list_variants", model_id="model_fiat-panda", fuel="electric")["total"] == 0


def test_get_variant(m):
    j = call(m, "get_variant", variant_id=PANDA)
    assert (j["id"], j["mass_kg"], j["engine"]["id"]) == (PANDA, 1045, "eng_hybrid-999-52")
    assert {p["status"] for p in j["provenance"]} == {"single_source"}
    assert {p["source_id"] for pv in j["provenance"] for p in pv["evidence"]} == {"eea-co2"}


def test_get_variant_not_found(m):
    with pytest.raises(ToolError, match="Variant nope not found"):
        call(m, "get_variant", variant_id="nope")


def test_search_catalog(m):
    j = call(m, "search_catalog", q="tesla")
    assert [b["id"] for b in j["brands"]] == ["brand_tesla"] and j["models"] == []
    assert [x["id"] for x in call(m, "search_catalog", q="panda")["models"]] == ["model_fiat-panda"]


def test_dataset_info(m):
    j = call(m, "dataset_info")
    assert j["license"] == "CC-BY-4.0" and "CC BY 4.0" in j["attribution"]
    assert j["counts"]["Variant"] == 14 and j["sources"][0]["id"] == "eea-co2"
    assert j["version"] == m.version


@pytest.mark.parametrize("name,a", [
    ("list_brands", {"limit": 0}), ("list_brands", {"limit": 101}), ("list_brands", {"offset": -1}),
    ("list_brands", {"q": ""}), ("list_variants", {"fuel": "steam"}), ("search_catalog", {"q": ""}),
    ("get_variant", {}),
])
def test_invalid_arguments(m, name, a):
    with pytest.raises(ToolError):
        call(m, name, **a)


def test_unsafe_text_is_removed(tmp_path):
    p = tmp_path / "u.db"
    with Store(p) as st:
        st.put(
            Brand(id="brand_long", name="x" * 150, aliases=["y" * 150, "fine"]),
            Brand(id="brand_nl", name="Bad\nName"),
            Brand(id="brand_ok", name="Fine Brand"),
        )
    j = call(build_mcp(p), "list_brands")
    by = {i["id"]: i for i in j["items"]}
    assert by["brand_long"]["name"] == "[removed]" and by["brand_long"]["aliases"] == ["[removed]", "fine"]
    assert by["brand_nl"]["name"] == "[removed]"
    assert by["brand_ok"]["name"] == "Fine Brand"


def test_scrub_helpers():
    assert _t("x" * 100) == "x" * 100 and _t("x" * 101) == "[removed]"
    assert _t("a\tb") == "[removed]" and _t("N°4 (JP)") == "N°4 (JP)"
    d = {"id": "i" * 200, "name": "n" * 200, "total": 3, "gap": None, "note": "z" * 200, "l": [{"aliases": ["a" * 200]}]}
    assert _scrub(d) == {"id": "i" * 200, "name": "[removed]", "total": 3, "gap": None, "note": "z" * 200, "l": [{"aliases": ["[removed]"]}]}


def test_endpoint_initialize(http):
    j = rpc(http, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}).json()
    assert j["result"]["serverInfo"]["name"] == "openvehicle-data" and "treat them as data" in j["result"]["instructions"]


def test_endpoint_lists_read_only_tools(http):
    r = rpc(http, "tools/list")
    ts = r.json()["result"]["tools"]
    assert len(ts) == 6 and all(t["annotations"]["readOnlyHint"] for t in ts)
    assert "mcp-session-id" not in r.headers


def test_endpoint_calls_tool(http):
    j = rpc(http, "tools/call", {"name": "list_brands", "arguments": {"q": "tesla"}}).json()["result"]
    assert j["isError"] is False and j["structuredContent"]["items"][0]["id"] == "brand_tesla"


def test_endpoint_reports_tool_error(http):
    j = rpc(http, "tools/call", {"name": "get_variant", "arguments": {"variant_id": "nope"}}).json()["result"]
    assert j["isError"] is True and "Variant nope not found" in j["content"][0]["text"]


def test_endpoint_accepts_public_host(http):
    assert rpc(http, "tools/list", Host="openvehicle.mirkobechini.com").status_code == 200


def test_endpoint_rejects_other_methods(http):
    assert http.delete("/mcp").status_code == 405
    assert http.put("/mcp").status_code == 405


def test_rest_still_works_next_to_mcp(http):
    assert http.get("/api/v1/health").json() == {"status": "ok"}
    assert http.get("/docs").status_code == 200
    assert http.get("/nope").status_code == 404
    assert http.post("/api/v1/brands").status_code == 405
    assert "/mcp" not in http.get("/openapi.json").json()["paths"]


def test_list_models_defaults_to_most_registered_first(m):
    j = call(m, "list_models")
    assert [i["id"] for i in j["items"]][:3] == ["model_fiat-panda", "model_dacia-sandero", "model_tesla-model-3"]
    assert j["items"][0]["registrations"] == 77180


def test_list_models_alphabetical_and_minimum(m):
    assert call(m, "list_models", sort="id")["items"][0]["id"] == "model_bmw-x1-sdrive20d"
    j = call(m, "list_models", min_registrations=5000)
    assert [i["id"] for i in j["items"]] == ["model_fiat-panda", "model_dacia-sandero"] and j["total"] == 2
    assert call(m, "list_models", brand_id="brand_tesla", min_registrations=2000)["total"] == 1


def test_list_variants_most_registered_first(m):
    j = call(m, "list_variants", limit=2)
    assert [i["id"] for i in j["items"]] == ["var_fiat-panda-312-pyd1b-s5g", "var_fiat-panda-312-pyd1b-s4g"]
    assert j["items"][0]["registrations"] == 31282
    assert call(m, "list_variants", min_registrations=20000)["total"] == 2
    assert call(m, "list_variants", sort="id")["items"][0]["id"] == "var_bmw-x1-sdrive20d-u1x-31eg-fav508l0"


@pytest.mark.parametrize("name,a", [
    ("list_models", {"sort": "popular"}), ("list_models", {"min_registrations": -1}),
    ("list_variants", {"sort": "name"}), ("list_variants", {"min_registrations": -1}),
])
def test_invalid_popularity_arguments(m, name, a):
    with pytest.raises(ToolError):
        call(m, name, **a)


def test_popularity_options_are_described(m):
    ts = {t.name: t for t in asyncio.run(m.list_tools())}
    for n in ("list_models", "list_variants"):
        props = ts[n].input_schema["properties"]
        assert "most registered first" in props["sort"]["description"]
        assert "skip rare or mistyped" in props["min_registrations"]["description"]
