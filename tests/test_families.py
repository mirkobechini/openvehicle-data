import json

import pytest
from pydantic import ValidationError

from pipeline.importers.families import BrandRules, FamilyRules, Rule, family_of, load_family_rules

R = "a long enough reason for the entry"


def fr(brand="TESTBRAND", rules=None):
    return FamilyRules.model_validate({"brands": {brand: {"reason": R, "rules": rules or [{"pattern": r"^(\S+)", "family": r"\1"}]}}})


def test_a_rule_needs_a_compilable_pattern_and_existing_groups():
    assert Rule(pattern=r"^(A)(\d)", family=r"\1-\2").family == r"\1-\2"
    assert Rule(pattern="^ABC", family="FIXED").family == "FIXED"
    for k in ({"pattern": "^(unclosed", "family": "X"}, {"pattern": r"^(A)", "family": r"\2"},
              {"pattern": "", "family": "X"}, {"pattern": "A", "family": ""}, {"pattern": "A", "family": "X", "note": "n"}):
        with pytest.raises(ValidationError):
            Rule(**k)


def test_brand_rules_need_a_reason_and_at_least_one_rule():
    r = {"pattern": "^A", "family": "A"}
    assert BrandRules(reason=R, rules=[r]).rules[0].family == "A"
    for k in ({"reason": "short", "rules": [r]}, {"reason": R, "rules": []}, {"reason": R}, {"reason": R, "rules": [r], "x": 1}):
        with pytest.raises(ValidationError):
            BrandRules(**k)


def test_brands_must_be_unique_ignoring_case_and_punctuation():
    r = {"reason": R, "rules": [{"pattern": "^A", "family": "A"}]}
    assert len(FamilyRules.model_validate({"brands": {"ROLLS ROYCE": r, "BMW": r}}).brands) == 2
    for d in ({"ROLLS ROYCE": r, "Rolls-Royce": r}, {"": r}, {"!!!": r}):
        with pytest.raises(ValidationError):
            FamilyRules.model_validate({"brands": d})
    assert FamilyRules().brands == {}


def test_load_from_a_custom_path(tmp_path):
    f = tmp_path / "f.json"
    f.write_text(json.dumps({"brands": {"BMW": {"reason": R, "rules": [{"pattern": r"^(X\d)", "family": r"\1"}]}}}), encoding="utf-8")
    assert family_of(load_family_rules(f), "BMW", "X1 SDRIVE18D") == "X1"


def test_the_first_matching_rule_wins():
    c = fr(rules=[{"pattern": r"^(A) ", "family": r"\1-CLASS"}, {"pattern": r"^(\S+)", "family": r"\1"}])
    assert family_of(c, "TESTBRAND", "A 180 D") == "A-CLASS"
    assert family_of(c, "TESTBRAND", "B 180 D") == "B"


def test_matching_ignores_case_and_the_family_is_upper_case_with_single_spaces():
    c = fr(rules=[{"pattern": r"^(id\.)  ?(\d)", "family": r"\1  \2"}])
    assert family_of(c, "TESTBRAND", "ID. 4 PRO") == "ID. 4"
    assert family_of(c, "TESTBRAND", "id.  4 pro") == "ID. 4"


def test_a_rule_that_gives_an_empty_family_falls_through_to_the_next_one():
    c = fr(rules=[{"pattern": r"^(X?)\d", "family": r"\1"}, {"pattern": r"^(\d)", "family": r"N\1"}])
    assert family_of(c, "TESTBRAND", "3 SERIES") == "N3"


def test_search_is_not_anchored_unless_the_pattern_says_so():
    c = fr(rules=[{"pattern": r"\b(COUNTRYMAN)\b", "family": r"\1"}])
    assert family_of(c, "TESTBRAND", "JCW COUNTRYMAN ALL4") == "COUNTRYMAN"


def test_no_match_leaves_the_name_alone():
    c = fr(rules=[{"pattern": r"^ZZZ", "family": "Z"}])
    assert family_of(c, "TESTBRAND", "PANDA 4X4") == "PANDA 4X4"


def test_a_brand_without_rules_keeps_every_name():
    assert family_of(fr(), "TOYOTA", "YARIS CROSS") == "YARIS CROSS"
    assert family_of(FamilyRules(), "TOYOTA", "YARIS CROSS") == "YARIS CROSS"


def test_the_brand_is_found_ignoring_case_and_punctuation():
    c = fr(brand="MERCEDES-BENZ", rules=[{"pattern": r"^(GL[A-Z])", "family": r"\1"}])
    for b in ("MERCEDES-BENZ", "mercedes benz", "Mercedes-Benz", "MERCEDESBENZ"):
        assert family_of(c, b, "GLC 220 D") == "GLC"
