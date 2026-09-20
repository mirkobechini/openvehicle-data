import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from core.models import Variant
from core.storage import Store
from pipeline import build as bd
from pipeline.export import DB, FILES

TODAY = date(2026, 9, 19)
RDW = "opendata.rdw.nl"
ROWS = json.loads((Path(__file__).parent / "fixtures" / "eea_sample.json").read_text(encoding="utf-8"))["results"]


def client(rows=ROWS):
    return httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=[] if r.url.host == RDW else {"results": rows})))


def test_build(tmp_path):
    r = bd.build(tmp_path / "o", "0.1.0", "2025", client=client(), today=TODAY)
    assert r["import"]["variants"] == 14 and r["import"]["conflicts"] == 0
    assert r["export"]["counts"]["variants"] == 14 and r["export"]["warnings"] == 0
    assert all((tmp_path / "o" / n).is_file() for n in FILES)
    with Store(tmp_path / "o" / DB, ro=True) as st:
        assert len(st.find(Variant)) == 14


def test_build_with_previous_export(tmp_path):
    bd.build(tmp_path / "v1", "0.1.0", "2025", client=client(), today=TODAY)
    rows = [r for r in ROWS if r["Cn"] != "SANDERO"]
    r = bd.build(tmp_path / "v2", "0.2.0", "2025", client=client(rows), prev=tmp_path / "v1", today=TODAY)
    assert r["export"]["previous"] == "0.1.0"
    ch = json.loads((tmp_path / "v2" / "changelog.json").read_text(encoding="utf-8"))["changes"]
    assert ch["brands"]["removed"] == ["brand_dacia"]


def test_temporary_database_is_removed(tmp_path, monkeypatch):
    seen = []
    real = bd.eea.run
    monkeypatch.setattr(bd.eea, "run", lambda db, *a: seen.append(Path(db)) or real(db, *a))
    bd.build(tmp_path / "o", "0.1.0", "2025", client=client(), today=TODAY)
    assert seen and not seen[0].exists()


def test_network_error_leaves_no_output(tmp_path):
    with pytest.raises(httpx.HTTPStatusError):
        bd.build(tmp_path / "o", "0.1.0", "2025", client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500))))
    assert not (tmp_path / "o").exists()


def test_bad_version_leaves_no_output(tmp_path):
    with pytest.raises(ValueError):
        bd.build(tmp_path / "o", "1.0", "2025", client=client(), today=TODAY)
    assert not (tmp_path / "o").exists()


def test_main(monkeypatch, capsys):
    calls = []
    fake = {"import": {"variants": 1}, "export": {"counts": {"variants": 1}, "warnings": 0}}
    monkeypatch.setattr(bd, "build", lambda *a, **k: calls.append((a, k)) or fake)
    bd.main(["--years", "2025", "--version", "0.1.0", "--out", "o"])
    bd.main(["--years", "2019-2024", "--version", "0.2.0", "--out", "p", "--country", "DE", "--prev", "o", "--skip-rdw"])
    assert calls == [(("o", "0.1.0", "2025", "IT", None), {"check": True}), (("p", "0.2.0", "2019-2024", "DE", "o"), {"check": False})]
    out = capsys.readouterr().out
    assert out.count('"warnings": 0') == 2 and '"variants": 1' in out


def test_build_several_years_and_compare_with_the_previous_release(tmp_path):
    import re

    def h(req):
        if req.url.host == RDW:
            return httpx.Response(200, json=[])
        q = req.url.params["query"]
        m = re.search(r"co2cars_(\d{4})", q) or re.search(r"\[Year\]=(\d{4})", q)
        return httpx.Response(200, json={"results": {2019: ROWS[:8], 2024: ROWS[4:], 2025: ROWS}[int(m[1])]})

    cl = httpx.Client(transport=httpx.MockTransport(h))
    r = bd.build(tmp_path / "o", "0.1.0", "2019,2024-2025", client=cl, today=TODAY)
    assert r["import"]["years"] == [2019, 2024, 2025] and r["import"]["variants"] == 14
    assert r["export"]["counts"]["variants"] == 14 and r["export"]["warnings"] == 0
    with Store(tmp_path / "o" / DB, ro=True) as st:
        v = st.get(Variant, "var_fiat-panda-312-pyd1b-s5g")
        assert (v.year_from, v.year_to) == (2019, 2025)


def test_build_rejects_unknown_years_before_fetching(tmp_path):
    seen = []
    cl = httpx.Client(transport=httpx.MockTransport(lambda r: seen.append(r) or httpx.Response(200, json={"results": []})))
    with pytest.raises(ValueError, match="2019-2025"):
        bd.build(tmp_path / "o", "0.1.0", "2015", client=cl, today=TODAY)
    assert seen == [] and not (tmp_path / "o").exists()


def test_build_cross_checks_with_rdw_from_the_first_year(tmp_path):
    seen = []

    def h(req):
        if req.url.host == RDW:
            seen.append(req.url.params["$where"])
            return httpx.Response(200, json=[{"merk": "FIAT", "type": "312", "variant": "PYD1B", "uitvoering": "S5G", "massa_rijklaar": "1045", "cilinderinhoud": "999", "wielbasis": "230", "n": "3"}])
        return httpx.Response(200, json={"results": ROWS})

    r = bd.build(tmp_path / "o", "0.1.0", "2024-2025", client=httpx.Client(transport=httpx.MockTransport(h)), today=TODAY)
    assert "20240101" in seen[0] and r["import"]["rdw"]["matched"] == 1 and r["import"]["rdw"]["confirmed"] >= 2
    with Store(tmp_path / "o" / DB, ro=True) as st:
        assert {p.status.value for p in st.prov("var_fiat-panda-312-pyd1b-s5g") if p.field == "mass_kg"} == {"confirmed"}


def test_build_can_skip_the_rdw_cross_check(tmp_path):
    seen = []
    h = lambda req: seen.append(req.url.host) or httpx.Response(200, json={"results": ROWS})
    r = bd.build(tmp_path / "o", "0.1.0", "2025", client=httpx.Client(transport=httpx.MockTransport(h)), today=TODAY, check=False)
    assert "rdw" not in r["import"] and RDW not in seen
