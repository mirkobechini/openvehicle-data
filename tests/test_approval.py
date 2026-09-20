import pytest

from core.approval import base


@pytest.mark.parametrize("s,b", [
    ("e3*2007/46*0064*05", "e3*2007/46*0064"), ("E3*2007/46*0064*05", "e3*2007/46*0064"), (" e13*2007/46*1234*00 ", "e13*2007/46*1234"),
    ("e3*2007/46*0064", "e3*2007/46*0064"), ("e11*NKSF99/99*0001*02", "e11*nksf99/99*0001"), ("e3*2001/116*0217*53", "e3*2001/116*0217"),
])
def test_base(s, b):
    assert base(s) == b


@pytest.mark.parametrize("s", [None, "", "None", "e3", "e3*2007/46", "x3*2007/46*0064*05", "e*2007/46*0064*05", "e3**0064*05", "e3*2007/46**05", "e3*20 07*0064*05", 12])
def test_not_an_approval_number(s):
    assert base(s) is None
