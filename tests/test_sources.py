from pipeline.sources import EEA, SOURCES


def test_registry():
    assert SOURCES == {"eea-co2": EEA}


def test_eea_license_checked():
    assert EEA.license == "CC-BY-4.0"
    assert EEA.usable
    assert str(EEA.license_checked) == "2026-09-19"
