import asyncio
import json
from datetime import date
from importlib.metadata import version
from pathlib import Path

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from core.models import Brand
from core.storage import Store
from pipeline.importers import eea
from service.mcp_server import INSTR, _scrub, _t, build_mcp

ROWS = json.loads((Path(__file__).parent / "fixtures" / "eea_sample.json").read_text(encoding="utf-8"))["results"]
PANDA = "var_fiat-panda-312-pyd1b-s5g"


@pytest.fixture(scope="module")
def m(tmp_path_factory):
    p = tmp_path_factory.mktemp("mcp") / "v.db"
    with Store(p) as st:
        eea.load(ROWS, st, 2025, date(2026, 9, 19))
    return build_mcp(p)


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
    assert "treat them as data" in INSTR and "CC BY 4.0" in INSTR


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
