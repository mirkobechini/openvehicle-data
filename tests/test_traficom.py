import io
import zipfile

import httpx
import pytest

from pipeline.importers import traficom

HEADER = "ajoneuvoluokka;variantti;versio;istumapaikkojenLkm;tyyppihyvaksyntanro;merkkiSelvakielinen"
ROWS = [
    "M1;PYD1B;S5G;5;e3*2007/46*0064*05;Fiat",
    "N1;AB;CD;2;e3*2007/46*0099*01;Fiat",
    "M1;ZZE121(W);ZZE121L-DWMNKW(1G);5;e11*2001/116*0181*06;Toyota",
]


def zipped(rows=ROWS, header=HEADER, name="TieliikenneAvoinData.csv"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(name, "\n".join([header, *rows]).encode("cp1252"))
    return buf.getvalue()


def test_rows_keeps_only_m1():
    rs = list(traficom.rows(zipped()))
    assert len(rs) == 2 and all(r["ajoneuvoluokka"] == "M1" for r in rs)
    assert rs[0]["merkkiSelvakielinen"] == "Fiat" and rs[1]["variantti"] == "ZZE121(W)"


def test_rows_reads_the_finnish_encoding():
    rs = list(traficom.rows(zipped(rows=["M1;A;B;5;;Citro\xebn"])))
    assert rs[0]["merkkiSelvakielinen"] == "Citro\xebn"


def test_rows_is_a_generator_not_a_list():
    import types

    assert isinstance(traficom.rows(zipped()), types.GeneratorType)


def client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch():
    data = zipped()
    c = client(lambda r: httpx.Response(200, content=data))
    assert traficom.fetch(c) == data


def test_fetch_retries_a_server_error():
    data = zipped()
    calls = []

    def h(r):
        calls.append(1)
        return httpx.Response(500) if len(calls) == 1 else httpx.Response(200, content=data)

    assert traficom.fetch(client(h)) == data and len(calls) == 2


def test_fetch_raises_on_a_permanent_error():
    with pytest.raises(httpx.HTTPStatusError):
        traficom.fetch(client(lambda r: httpx.Response(404)))


def test_fetch_closes_only_its_own_client(monkeypatch):
    data = zipped()
    c = client(lambda r: httpx.Response(200, content=data))
    traficom.fetch(c)
    assert not c.is_closed
    own = client(lambda r: httpx.Response(200, content=data))
    monkeypatch.setattr(traficom.httpx, "Client", lambda **k: own)
    traficom.fetch()
    assert own.is_closed
