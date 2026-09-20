from pipeline.sources import EEA, RDW, SOURCES


def test_registry():
    assert SOURCES == {"eea-co2": EEA, "rdw-nl": RDW}


def test_eea_license_checked():
    assert EEA.license == "CC-BY-4.0"
    assert EEA.usable
    assert str(EEA.license_checked) == "2026-09-20"
    assert "DG Climate Action" in EEA.name


def test_rdw_license_checked():
    assert RDW.license == "Public-Domain"
    assert RDW.usable
    assert str(RDW.license_checked) == "2026-09-20"
