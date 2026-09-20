import pytest
from core.ids import make_id, slug


def test_slug():
    assert slug("Citroën C3 Aircross") == "citroen-c3-aircross"
    assert slug("  Alfa  Romeo! ") == "alfa-romeo"


def test_make_id():
    assert make_id("brand", "Fiat") == "brand_fiat"
    assert make_id("eng", "petrol", 1242, 51.5) == "eng_petrol-1242-51-5"


def test_deterministic():
    assert make_id("model", "Fiat", "500") == make_id("model", "FIAT", " 500 ")


def test_empty():
    with pytest.raises(ValueError):
        make_id("brand", "!!!")


def test_plus_sign_is_kept_as_a_word():
    assert slug("EQA 250+") == "eqa-250-plus"
    assert slug("MG3 HYBRID+") == "mg3-hybrid-plus"
    assert slug("A+B") == "a-plus-b"
    assert make_id("model", "MERCEDES-BENZ", "EQA 250+") != make_id("model", "MERCEDES-BENZ", "EQA 250")
