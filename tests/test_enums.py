import pytest
from core.enums import Category, Fuel


def test_category():
    assert [c.value for c in Category] == ["M1"]


def test_fuel():
    assert Fuel("electric") is Fuel.ELECTRIC
    assert len(Fuel) == 9


def test_bad():
    with pytest.raises(ValueError):
        Fuel("steam")
