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
ROWS = json.loads((Path(__file__).parent / "fixtures" / "eea_sample.json").read_text(encoding="utf-8"))["results"]


def client(rows=ROWS):
    return httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"results": rows})))


def test_build(tmp_path):
    r = bd.build(tmp_path / "o", "0.1.0", "t1", 2025, client=client(), today=TODAY)
    assert r["import"]["variants"] == 14 and r["import"]["conflicts"] == 0
    assert r["export"]["counts"]["variants"] == 14 and r["export"]["warnings"] == 0
    assert all((tmp_path / "o" / n).is_file() for n in FILES)
    with Store(tmp_path / "o" / DB, ro=True) as st:
        assert len(st.find(Variant)) == 14


def test_build_with_previous_export(tmp_path):
    bd.build(tmp_path / "v1", "0.1.0", "t1", 2025, client=client(), today=TODAY)
    rows = [r for r in ROWS if r["Cn"] != "SANDERO"]
    r = bd.build(tmp_path / "v2", "0.2.0", "t1", 2025, client=client(rows), prev=tmp_path / "v1", today=TODAY)
    assert r["export"]["previous"] == "0.1.0"
    ch = json.loads((tmp_path / "v2" / "changelog.json").read_text(encoding="utf-8"))["changes"]
    assert ch["brands"]["removed"] == ["brand_dacia"]


def test_temporary_database_is_removed(tmp_path, monkeypatch):
    seen = []
    real = bd.eea.run
    monkeypatch.setattr(bd.eea, "run", lambda db, *a: seen.append(Path(db)) or real(db, *a))
    bd.build(tmp_path / "o", "0.1.0", "t1", 2025, client=client(), today=TODAY)
    assert seen and not seen[0].exists()


def test_network_error_leaves_no_output(tmp_path):
    with pytest.raises(httpx.HTTPStatusError):
        bd.build(tmp_path / "o", "0.1.0", "t1", 2025, client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500))))
    assert not (tmp_path / "o").exists()


def test_bad_version_leaves_no_output(tmp_path):
    with pytest.raises(ValueError):
        bd.build(tmp_path / "o", "1.0", "t1", 2025, client=client(), today=TODAY)
    assert not (tmp_path / "o").exists()


def test_main(monkeypatch, capsys):
    calls = []
    fake = {"import": {"variants": 1}, "export": {"counts": {"variants": 1}, "warnings": 0}}
    monkeypatch.setattr(bd, "build", lambda *a: calls.append(a) or fake)
    bd.main(["--table", "t", "--year", "2025", "--version", "0.1.0", "--out", "o"])
    bd.main(["--table", "t", "--year", "2024", "--version", "0.2.0", "--out", "p", "--country", "DE", "--prev", "o"])
    assert calls == [("o", "0.1.0", "t", 2025, "IT", None), ("p", "0.2.0", "t", 2024, "DE", "o")]
    out = capsys.readouterr().out
    assert out.count('"warnings": 0') == 2 and '"variants": 1' in out
