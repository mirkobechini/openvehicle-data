import httpx
import pytest

from pipeline import http
from pipeline.importers import eea, rdw


def seq(*codes, body=None):
    calls = []

    def h(req):
        calls.append(req.url.path)
        c = codes[min(len(calls), len(codes)) - 1]
        if isinstance(c, Exception):
            raise c
        return httpx.Response(c, json={"results": [], "ok": 1} if body is None else body)

    return httpx.Client(transport=httpx.MockTransport(h)), calls


@pytest.mark.parametrize("first", [500, 502, 503, 429, httpx.ConnectError("x"), httpx.ReadTimeout("x")])
def test_a_transient_failure_is_retried(first):
    c, calls = seq(first, first, 200)
    assert http.get(c, "http://x/a").json()["ok"] == 1 and len(calls) == 3


def test_it_gives_up_after_the_last_wait_with_the_original_error(monkeypatch):
    slept = []
    monkeypatch.setattr(http.time, "sleep", slept.append)
    monkeypatch.setattr(http, "DELAYS", (5, 20, 60))
    c, calls = seq(503)
    with pytest.raises(httpx.HTTPStatusError) as e:
        http.get(c, "http://x/a")
    assert e.value.response.status_code == 503 and len(calls) == 4 and slept == [5, 20, 60]
    c, calls = seq(httpx.ConnectError("boom"))
    with pytest.raises(httpx.ConnectError):
        http.get(c, "http://x/a")
    assert len(calls) == 4


@pytest.mark.parametrize("code", [200, 400, 404])
def test_success_and_client_errors_are_returned_at_once(code):
    c, calls = seq(code)
    assert http.get(c, "http://x/a").status_code == code and len(calls) == 1


def test_the_eea_download_survives_a_server_error():
    c, calls = seq(500, 200)
    assert eea.fetch("co2cars_2025Pv31", client=c) == [] and len(calls) == 2


def test_the_rdw_downloads_survive_a_server_error():
    c, calls = seq(500, 200, body=[])
    assert rdw.fetch(2019, client=c) == [] and len(calls) == 2
    c, calls = seq(502, 200, body=[])
    assert dict(rdw.fetch_fuel(["AB123C"], client=c)) == {} and len(calls) == 2


def test_a_permanent_rdw_fuel_error_still_hides_the_plates():
    c, _ = seq(500)
    with pytest.raises(RuntimeError) as e:
        rdw.fetch_fuel(["SECRET1"], client=c)
    assert "SECRET1" not in str(e.value) and "SECRET1" not in repr(e.value.__cause__)
