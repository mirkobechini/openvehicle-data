from pipeline.sources import EEA, RDW, SOURCES, WIKIDATA


def test_registry():
    assert SOURCES == {"eea-co2": EEA, "rdw-nl": RDW, "wikidata": WIKIDATA}


def test_eea_license_checked():
    assert EEA.license == "CC-BY-4.0"
    assert EEA.usable
    assert str(EEA.license_checked) == "2026-09-20"
    assert "DG Climate Action" in EEA.name


def test_rdw_license_checked():
    assert RDW.license == "Public-Domain"
    assert RDW.usable
    assert str(RDW.license_checked) == "2026-09-20"


def test_wikidata_license_checked():
    assert WIKIDATA.license == "CC0-1.0"
    assert WIKIDATA.usable
    assert str(WIKIDATA.license_checked) == "2026-09-20"
