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


def merge(**k):
    return {"brand": "TOYOTA", "model": "YARIS GR", "into": "GR YARIS", "reason": R, **k}


def test_merges_are_loaded_and_default_to_none():
    assert Corrections().merge_models == []
    c = Corrections.model_validate({"merge_models": [merge()]})
    assert (c.merge_models[0].model, c.merge_models[0].into) == ("YARIS GR", "GR YARIS")


@pytest.mark.parametrize("d", [
    {"merge_models": [merge(into="Yaris-GR")]},
    {"merge_models": [merge(into="!!!")]},
    {"merge_models": [merge(reason="short")]},
    {"merge_models": [merge(brand="")]},
    {"merge_models": [merge(extra="x")]},
    {"merge_models": [merge(), merge(brand="Toyota", model="yaris gr", into="OTHER")]},
    {"merge_models": [merge(), merge(model="GR YARIS", into="GR SPORT")]},
    {"merge_models": [merge()], "exclude_models": [{"brand": "TOYOTA", "model": "YARIS GR", "reason": R}]},
])
def test_invalid_merges(d):
    with pytest.raises(ValidationError):
        Corrections.model_validate(d)


def test_the_same_model_name_of_different_brands_can_be_merged_separately():
    c = Corrections.model_validate({"merge_models": [merge(), merge(brand="SUBARU", model="YARIS GR")]})
    assert len(c.merge_models) == 2


def test_shipped_merges_have_reasons():
    ms = load_corrections().merge_models
    assert {(x.brand, x.model, x.into) for x in ms} >= {("TOYOTA", "YARIS GR", "GR YARIS"), ("FIAT", "500 ABARTH", "ABARTH 500")}
    assert all(len(x.reason) >= 10 for x in ms)


def test_shipped_older_year_corrections():
    c = load_corrections()
    assert c.brands["BMW I"] == "BMW" and c.brands["FORD W GMBH"] == "FORD"
    assert c.brands["MITSUBISHI MOTORS CORPORATION"] == "MITSUBISHI"
    assert c.brands["PAGANI S.P.A."] == "PAGANI" and c.brands["AUTOMOBILI LAMBORGHINI S.P.A."] == "LAMBORGHINI"
    assert ("AUDI", "PANDA") in {(x.brand, x.model) for x in c.exclude_models}
