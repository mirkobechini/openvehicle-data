import json

import pytest
from pydantic import ValidationError

from pipeline.importers.corrections import PATH, Corrections, load_corrections

R = "a long enough reason for the entry"


def test_shipped_file_is_valid():
    c = load_corrections()
    assert len(c.brands) >= 7 and len(c.exclude_models) >= 2
    assert c.brands["VW"] == "VOLKSWAGEN" and c.brands["SSANGJONG"] == "SSANGYONG"
    assert {(x.brand, x.model) for x in c.exclude_models} >= {("FIAT", "GOLF"), ("FIAT", "AVENGER")}
    assert all(len(x.reason) >= 10 for x in c.exclude_models)


def test_shipped_file_is_next_to_the_module():
    assert PATH.name == "corrections.json" and PATH.is_file()


def test_load_from_custom_path(tmp_path):
    f = tmp_path / "c.json"
    f.write_text(json.dumps({"brands": {"VW": "VOLKSWAGEN"}, "exclude_models": [{"brand": "FIAT", "model": "GOLF", "reason": R}]}), encoding="utf-8")
    c = load_corrections(f)
    assert c.brands == {"VW": "VOLKSWAGEN"} and c.exclude_models[0].model == "GOLF"


def test_empty_corrections_are_valid():
    c = Corrections()
    assert c.brands == {} and c.exclude_models == []


@pytest.mark.parametrize("d", [
    {"brands": {"VW": "VW"}},
    {"brands": {"V-W": "vw"}},
    {"brands": {"VW": "VOLKSWAGEN", "V W": "VOLKSWAGEN"}},
    {"brands": {"A": "B", "B": "C"}},
    {"brands": {"": "VOLKSWAGEN"}},
    {"brands": {"VW": "!!!"}},
    {"exclude_models": [{"brand": "FIAT", "model": "GOLF", "reason": "short"}]},
    {"exclude_models": [{"brand": "", "model": "GOLF", "reason": R}]},
    {"exclude_models": [{"brand": "FIAT", "model": "GOLF", "reason": R}, {"brand": "Fiat", "model": "golf", "reason": R}]},
    {"exclude_models": [{"brand": "FIAT", "model": "GOLF", "reason": R, "note": "x"}]},
    {"unknown": 1},
])
def test_invalid_corrections(d):
    with pytest.raises(ValidationError):
        Corrections.model_validate(d)


def test_same_model_of_different_brands_is_allowed():
    c = Corrections.model_validate({"exclude_models": [{"brand": "FIAT", "model": "GOLF", "reason": R}, {"brand": "SEAT", "model": "GOLF", "reason": R}]})
    assert len(c.exclude_models) == 2
