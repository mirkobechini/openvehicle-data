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


SHIPPED = load_family_rules()


def test_the_shipped_rules_are_valid_and_each_brand_has_a_reason():
    assert len(SHIPPED.brands) >= 50
    assert all(len(b.reason) >= 10 and b.rules for b in SHIPPED.brands.values())


@pytest.mark.parametrize("brand,name,family", [
    ("BMW", "X1 SDRIVE18D", "X1"), ("BMW", "X3SDRIVE 18D", "X3"), ("BMW", "IX1 EDRIVE20", "IX1"), ("BMW", "IX XDRIVE40", "IX"),
    ("BMW", "XM 50E", "XM"), ("BMW", "118D", "1 SERIES"), ("BMW", "120", "1 SERIES"), ("BMW", "218D ACTIVE TOURER", "2 SERIES"),
    ("BMW", "M340D", "3 SERIES"), ("BMW", "520D XDRIVE", "5 SERIES"), ("BMW", "I4 EDRIVE40", "I4"), ("BMW", "M5", "M5"), ("BMW", "Z4", "Z4"),
    ("MERCEDES-BENZ", "GLC 220 D 4MATIC", "GLC"), ("MERCEDES-BENZ", "AMG GLC 43 4MATIC", "GLC"), ("MERCEDES-BENZ", "CLA 200 D", "CLA"),
    ("MERCEDES-BENZ", "AMG A 35 4MATIC", "A-CLASS"), ("MERCEDES-BENZ", "C 220D 4MATIC ALL-TERRAIN", "C-CLASS"),
    ("MERCEDES-BENZ", "G 450 D", "G-CLASS"), ("MERCEDES-BENZ", "EQA 250+", "EQA"), ("MERCEDES-BENZ", "AMG EQE 43 4MATIC", "EQE"),
    ("MERCEDES-BENZ", "VITO TOURER", "VITO"), ("MERCEDES-BENZ", "EVITO TOURER", "VITO"), ("MERCEDES-BENZ", "ECITAN TOURER", "CITAN"),
    ("MERCEDES-BENZ", "MB SPRINTER", "SPRINTER"), ("MERCEDES-BENZ", "V-KLASSE", "V-KLASSE"), ("MERCEDES-BENZ", "T-CLASS", "T-CLASS"),
    ("MERCEDES-AMG", "AMG GT 63 4MATIC+", "AMG GT"), ("MERCEDES-AMG", "AMG SL 43", "AMG SL"), ("MERCEDES-AMG", "AMG ONE", "AMG ONE"),
    ("AUDI", "A3 SPORTBACK", "A3"), ("AUDI", "Q5 SB", "Q5"), ("AUDI", "Q4 SPORTBACK 45 E-TRON", "Q4"), ("AUDI", "A6 AV E-TRON PERFORMANCE", "A6"),
    ("AUDI", "RS 3 SPORTBACK", "RS 3"), ("AUDI", "SQ5 SB", "SQ5"), ("AUDI", "S3 LIMOUSINE", "S3"), ("AUDI", "RS E-TRON GT PERFORMANCE", "E-TRON GT"),
    ("AUDI", "E-TRON GT", "E-TRON GT"), ("AUDI", "R8 COUPE", "R8 COUPE"), ("AUDI", "A8", "A8"),
    ("PORSCHE", "911 CARRERA 4 GTS", "911"), ("PORSCHE", "718 CAYMAN GT4 RS", "718"), ("PORSCHE", "MACAN 4S", "MACAN"), ("PORSCHE", "TAYCAN TURBO S", "TAYCAN"),
    ("VOLKSWAGEN", "ID.4 PRO 210 KW", "ID.4"), ("VOLKSWAGEN", "ID.7 TOURER PRO S", "ID.7"), ("VOLKSWAGEN", "ID. BUZZ PRO LR 210 KW", "ID. BUZZ"),
    ("VOLKSWAGEN", "TOUAREG EHYBRID", "TOUAREG"), ("VOLKSWAGEN", "CADDY F-STYLE WAV", "CADDY"),
    ("VOLKSWAGEN", "T CROSS", "T CROSS"), ("VOLKSWAGEN", "T-ROC", "T-ROC"), ("VOLKSWAGEN", "GOLF", "GOLF"), ("VOLKSWAGEN", "TRANSPORTER CARAVELLE", "TRANSPORTER CARAVELLE"),
    ("MASERATI", "GRECALE TROFEO", "GRECALE"), ("MASERATI", "MC PURA CIELO", "MC PURA"), ("MASERATI", "MC20 CIELO", "MC20"), ("MASERATI", "GT2STRADALE", "GT2STRADALE"),
    ("FERRARI", "SF 90 XX STRADALE", "SF90"), ("FERRARI", "SF90 SPIDER", "SF90"), ("FERRARI", "12 CILINDRI SPIDER", "12CILINDRI"), ("FERRARI", "296 GTS", "296"), ("FERRARI", "ROMA SPIDER", "ROMA"),
    ("CUPRA", "BORN 170 KW 60 63 KWH", "BORN"), ("CUPRA", "LEON SP E-HYBRID150", "LEON"),
    ("MINI", "JCW COUNTRYMAN ALL4", "COUNTRYMAN"), ("MINI", "COOPER SE", "COOPER"), ("MINI", "JCW E", "JCW"), ("MINI", "CLUBMAN COOPER D", "CLUBMAN"), ("MINI", "JCW ACEMAN E", "ACEMAN"),
    ("LEXUS", "NX450H+", "NX"), ("LEXUS", "LC500", "LC"), ("LEXUS", "LBX", "LBX"),
    ("SKODA", "ENYAQ 85X", "ENYAQ"), ("SKODA", "OCTAVIA RS", "OCTAVIA"), ("VOLVO", "V60 CROSS COUNTRY", "V60"), ("VOLVO", "XC40", "XC40"),
    ("HYUNDAI", "IONIQ5 N", "IONIQ 5"), ("HYUNDAI", "IONIQ 5", "IONIQ 5"), ("HYUNDAI", "IONIQ 6", "IONIQ 6"), ("HYUNDAI", "I 30", "I30"),
    ("HYUNDAI", "I20 BI-FUEL", "I20"), ("HYUNDAI", "KONA, KAUAI", "KONA"), ("HYUNDAI", "TUCSON, IX35", "TUCSON"),
    ("RENAULT", "CAPTUR E-TECH HYBRID", "CAPTUR"), ("RENAULT", "5 E-TECH ELECTRIC", "5"), ("OPEL", "ASTRA SPORTS TOURER", "ASTRA"),
    ("BENTLEY", "CONTINENTAL GTC SPEED", "CONTINENTAL"), ("ROLLS ROYCE", "BLACK BADGE GHOST", "GHOST"),
])
def test_shipped_rules_on_real_names(brand, name, family):
    assert family_of(SHIPPED, brand, name) == family


@pytest.mark.parametrize("brand,name", [
    ("TESLA", "MODEL 3"), ("DR", "EVO 5"), ("LANCIA", "YPSILON"), ("JAGUAR", "E-PACE"),
])
def test_brands_without_rules_keep_every_model_apart(brand, name):
    assert family_of(SHIPPED, brand, name) == name


def test_a_model_of_the_related_car_is_not_pulled_into_another_family():
    assert family_of(SHIPPED, "AUDI", "Q4 45 E-TRON") != family_of(SHIPPED, "AUDI", "E-TRON GT")
    assert family_of(SHIPPED, "MERCEDES-BENZ", "GLC 220 D") != family_of(SHIPPED, "MERCEDES-BENZ", "GLA 200 D")
    assert family_of(SHIPPED, "BMW", "X1 SDRIVE18D") != family_of(SHIPPED, "BMW", "IX1 EDRIVE20")


@pytest.mark.parametrize("brand,name,family", [
    ("FIAT", "PANDA 4X4", "PANDA"), ("FIAT", "E-DOBLO", "DOBLO"), ("FIAT", "DOBLO' OLMEDO", "DOBLO"), ("FIAT", "DUCATO TWIN ARM", "DUCATO"),
    ("FIAT", "QUBO IMOBILITY", "QUBO"), ("FIAT", "500 HYBRID", "500"), ("FIAT", "500", "500"), ("FIAT", "500X", "500X"), ("FIAT", "500L", "500L"),
    ("FIAT", "500 ABARTH - NEWTRON", "ABARTH 500"), ("FIAT", "ABARTH 500", "ABARTH 500"), ("FIAT", "ABARTH 124 SPIDER", "124 SPIDER"),
    ("TOYOTA", "YARIS HYBRID", "YARIS"), ("TOYOTA", "YARIS CROSS VAN", "YARIS CROSS"), ("TOYOTA", "GR YARIS", "GR YARIS"),
    ("TOYOTA", "PRIUS PHEV", "PRIUS"), ("TOYOTA", "PROACE CITY VERSO ELECTRIC", "PROACE CITY"), ("TOYOTA", "PROACE F-STYLE WAV", "PROACE"),
    ("TOYOTA", "LAND CRUISER (150 SERIES)", "LAND CRUISER"), ("TOYOTA", "CH-R VAN", "C-HR"), ("TOYOTA", "GR 86", "86"), ("TOYOTA", "C-HR", "C-HR"),
    ("PEUGEOT", "E-RIFTER", "RIFTER"), ("PEUGEOT", "RIFTER OLMEDO", "RIFTER"), ("PEUGEOT", "EXPERT TRAVELLER TREK", "TRAVELLER"),
    ("PEUGEOT", "TRAVELLER", "TRAVELLER"), ("PEUGEOT", "PARTNER 4X4", "PARTNER"), ("PEUGEOT", "BOXER TWIN ARM", "BOXER"),
    ("PEUGEOT", "3008 VAN", "3008"), ("PEUGEOT", "3008 - 5008", "3008 - 5008"), ("PEUGEOT", "EXPERT", "EXPERT"), ("PEUGEOT", "208", "208"),
    ("CITROEN", "E-C3", "C3"), ("CITROEN", "E-C3 AIRCROSS", "C3 AIRCROSS"), ("CITROEN", "C4X", "C4 X"), ("CITROEN", "E-C4 X", "C4 X"),
    ("CITROEN", "E-C4", "C4"), ("CITROEN", "C5 AIRCROSS VAN", "C5 AIRCROSS"), ("CITROEN", "SPACETOURER", "C4 SPACETOURER"),
    ("CITROEN", "JUMPY SPACETOURER", "JUMPY"), ("CITROEN", "E-BERLINGO", "BERLINGO"), ("CITROEN", "BERLINGO-ROLFI", "BERLINGO"), ("CITROEN", "C4 CACTUS", "C4 CACTUS"),
    ("FORD", "TOURNEO CONNECT OLMEDO", "TOURNEO CONNECT"), ("FORD", "TRANSIT CUSTOM-FOCACCIA WAV", "TRANSIT CUSTOM"), ("FORD", "TRANSIT", "TRANSIT"),
    ("FORD", "TRANSIT \"VISION-AMBULANZE SRL\"", "TRANSIT"), ("FORD", "MONDEO HYBRID", "MONDEO"), ("FORD", "GRAND CMAX", "C-MAX"), ("FORD", "SMAX", "S-MAX"),
    ("FORD", "MUSTANG MACH-E", "MUSTANG MACH-E"), ("FORD", "PUMA", "PUMA"),
    ("KIA", "CEE'D", "CEED"), ("KIA", "XCEED", "XCEED"), ("KIA", "NIRO GPL", "NIRO"), ("KIA", "SOUL EMOTION", "SOUL"), ("KIA", "EV9 GT", "EV9"), ("KIA", "EV6 GT", "EV6"),
    ("NISSAN", "LEAF 40KWH", "LEAF"), ("NISSAN", "MICRA BIFUEL", "MICRA"), ("NISSAN", "JUKE BIFUEL", "JUKE"), ("NISSAN", "E-NV 200", "E-NV200"), ("NISSAN", "QASHQAI", "QASHQAI"),
    ("SEAT", "LEON SP E-HYBRID150", "LEON"), ("SEAT", "CUPRA LEON", "LEON"), ("SEAT", "CUPRA ATECA", "ATECA"), ("SEAT", "ARONA", "ARONA"),
    ("SMART", "EQ FORTWO COUPE", "FORTWO"), ("SMART", "FORTWO CABRIO BRABUS", "FORTWO"), ("SMART", "EQ FORFOUR", "FORFOUR"), ("SMART", "#1", "#1"),
    ("DS", "7 CROSSBACK", "DS 7"), ("DS", "DS7", "DS 7"), ("DS", "3 CROSSBACK", "DS 3 CROSSBACK"), ("DS", "DS3", "DS 3"), ("DS", "3 CABRIO", "DS 3"),
    ("DS", "4", "DS 4"), ("DS", "DS4", "DS 4"), ("DS", "9", "DS 9"), ("DS", "N 8", "N 8"),
    ("MG", "MG3 HYBRID+", "MG3"), ("MG", "MG4 ELECTRIC", "MG4"), ("MG", "MG5 ELECTRIC", "MG5"), ("MG", "ZS EV", "ZS"), ("MG", "EHS PLUG-IN HYBRID", "HS"), ("MG", "HS HYBRID+", "HS"),
    ("ALFA ROMEO", "STELVIO QUADRIFOGLIO", "STELVIO"), ("ALFA ROMEO", "ALFA GIULIETTA", "GIULIETTA"), ("ALFA ROMEO", "ALFA MITO", "MITO"),
    ("ALFA ROMEO", "GIULIA GTAM", "GIULIA"), ("ALFA ROMEO", "4C SPIDER", "4C"), ("ALFA ROMEO", "TONALE", "TONALE"),
    ("JEEP", "GRAND CHEROKEE SRT", "GRAND CHEROKEE"), ("JEEP", "WRANGLER UNLIMITED ROCK'S", "WRANGLER"), ("JEEP", "COMPASS VAN", "COMPASS"), ("JEEP", "RENEGADE", "RENEGADE"),
    ("DACIA", "DOKKER OLMEDO", "DOKKER"), ("DACIA", "SANDERO", "SANDERO"), ("MAZDA", "MAZDA2 HYBRID", "MAZDA2"), ("MAZDA", "CX-30", "CX-30"),
    ("HONDA", "CIVIC TYPE R", "CIVIC"), ("HONDA", "CIVIC 5DR", "CIVIC"), ("HONDA", "JAZZ", "JAZZ"),
    ("BYD", "SEAL U DM-I", "SEAL U"), ("BYD", "SEAL 6 DM-I TOURING", "SEAL 6"), ("BYD", "DOLPHIN SURF", "DOLPHIN"), ("BYD", "SEAL", "SEAL"), ("BYD", "ATTO 3", "ATTO 3"),
    ("SUZUKI", "JIMNY OLMEDO ZMODE GAN #05", "JIMNY"), ("SUZUKI", "JIMMY GAN 01", "JIMNY"), ("SUZUKI", "OLMEDO-ZMODE", "JIMNY"), ("SUZUKI", "E VITARA", "VITARA"),
    ("SUZUKI", "SWIFT", "SWIFT"),
])
def test_shipped_rules_for_the_second_group_of_brands(brand, name, family):
    assert family_of(SHIPPED, brand, name) == family


@pytest.mark.parametrize("brand,name,family", [
    ("SSANGYONG", "KORANDO E-MOTION", "KORANDO"), ("SSANGYONG", "TORRES EVX", "TORRES"), ("SSANGYONG", "TIVOLI", "TIVOLI"),
    ("ASTON MARTIN", "DB12 VOLANTE", "DB12"), ("ASTON MARTIN", "DB11 AMR", "DB11"), ("ASTON MARTIN", "DBS 770 ULTIMATE VOLANTE", "DBS"),
    ("ASTON MARTIN", "DBX707", "DBX"), ("ASTON MARTIN", "V12 VANTAGE ROADSTER", "V12 VANTAGE"), ("ASTON MARTIN", "VANTAGE ROADSTER F1 EDITION", "VANTAGE"),
    ("ASTON MARTIN", "VANQUISH", "VANQUISH"),
    ("CIRELLI", "5 BIFUEL CROSS", "5"), ("CIRELLI", "4 PLUG-IN", "4"), ("CIRELLI", "3 SPORT", "3"), ("CIRELLI", "SPORT COUPE'", "SPORT COUPE'"),
    ("EMC", "SEI GPL", "SEI"), ("EMC", "SEI", "SEI"), ("EMC", "WAVE 3 GPL", "WAVE 3"), ("EMC", "WAVE 2", "WAVE 2"), ("EMC", "SETTE", "SETTE"),
    ("MAHINDRA", "KUV 100 NXT LPG", "KUV 100"), ("MAHINDRA", "XUV 500", "XUV 500"),
    ("LOTUS", "EMIRA V6 MANUAL SPORT CHASSIS", "EMIRA"), ("LOTUS", "ELETRE", "ELETRE"),
    ("FORTHING", "FRIDAY 1.5T DCT DUAL-FUEL", "FRIDAY"), ("FORTHING", "U-TOUR 1.5T DCT 5 DUAL FUEL", "U-TOUR"), ("FORTHING", "T5 HEV 1.5T", "T5"),
    ("DONGFENG", "BOX PREMIUM", "BOX"), ("DONGFENG", "FREE", "FREE"),
    ("OMODA", "OMODA5 EV", "OMODA5"), ("OMODA", "5", "OMODA5"), ("OMODA", "9 PHEV", "9"),
    ("JAECOO", "JAECOO7 PHEV", "JAECOO7"), ("JAECOO", "JAECOO5", "JAECOO5"),
    ("SUBARU", "BRZ TOUGE", "BRZ"), ("SUBARU", "CROSSTRECK", "CROSSTREK"), ("SUBARU", "CROSSTREK", "CROSSTREK"), ("SUBARU", "XV", "XV"),
    ("MORGAN", "PLUS SIX SUPERSPORT", "PLUS SIX"), ("MORGAN", "PLUS FOUR 1909", "PLUS FOUR"), ("MORGAN", "MIDSUMMER", "MIDSUMMER"),
])
def test_shipped_rules_for_the_smaller_brands(brand, name, family):
    assert family_of(SHIPPED, brand, name) == family


@pytest.mark.parametrize("brand,name,family", [
    ("MCLAREN", "570S SPIDER", "570S"), ("MCLAREN", "570S COUPE", "570S"), ("MCLAREN", "750S COUPE'", "750S"), ("MCLAREN", "ARTURA SPIDE", "ARTURA"),
    ("MCLAREN", "ARTURA", "ARTURA"), ("MCLAREN", "570GT", "570GT"), ("MCLAREN", "GTS", "GTS"),
    ("CATERHAM", "SEVEN SV", "SEVEN"), ("CATERHAM", "SEVEN CSR", "SEVEN"), ("CATERHAM", "SEVEN S3", "SEVEN"),
])
def test_shipped_rules_for_mclaren_and_caterham(brand, name, family):
    assert family_of(SHIPPED, brand, name) == family
