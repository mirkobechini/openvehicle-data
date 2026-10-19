import json
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from core.models import Variant
from core.storage import Store
from pipeline.importers import eea
from service import queries as qs
from service.queries import VariantQuery

ROWS = json.loads((Path(__file__).parent / "fixtures" / "eea_sample.json").read_text(encoding="utf-8"))["results"]


@pytest.fixture(scope="module")
def st(tmp_path_factory):
    with Store(tmp_path_factory.mktemp("vq") / "v.db") as s:
        eea.load(ROWS, s, 2025, date(2026, 9, 19))
        yield s


def test_defaults_filter_nothing(st):
    r = qs.variants_page(st, (5, 0), VariantQuery())
    assert r["total"] == st.count(Variant) == 14 and r["count"] == 5


@pytest.mark.parametrize("k,v", [("q", ""), ("year", 1800), ("year", 2200), ("min_registrations", -1), ("sort", "name"), ("fuel", "steam"), ("type_approval", "x"), ("type_code", ""), ("version_code", "x" * 41)])
def test_query_validates_its_fields(k, v):
    with pytest.raises(ValidationError):
        VariantQuery(**{k: v})


def test_filters_intersect_and_never_unite(st):
    fiat = qs.variants_page(st, (200, 0), VariantQuery(brand_id="brand_fiat"))["total"]
    both = qs.variants_page(st, (200, 0), VariantQuery(brand_id="brand_fiat", model_id="model_fiat-panda"))["total"]
    assert 0 < both <= fiat
    assert qs.variants_page(st, (200, 0), VariantQuery(model_id="model_fiat-panda", family_id="family_bmw-x1"))["total"] == 0


def test_unknown_ids_still_raise(st):
    with pytest.raises(LookupError):
        qs.variants_page(st, (5, 0), VariantQuery(brand_id="brand_nope"))
