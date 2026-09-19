import importlib
import pytest

@pytest.mark.parametrize("n", ["core", "pipeline", "service"])
def test_import(n):
    assert importlib.import_module(n)
