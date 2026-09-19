import csv
import hashlib
import json
from datetime import date
from pathlib import Path

import pytest

from core.models import Brand, CarModel, Engine, Generation, Variant
from core.storage import Store
from pipeline.export import DB, FILES, LEGAL, PC, export
from pipeline.importers import eea
from pipeline.sources import EEA
from pipeline.validation import BuildError

TODAY = date(2026, 9, 19)
ROWS = json.loads((Path(__file__).parent / "fixtures" / "eea_sample.json").read_text(encoding="utf-8"))["results"]


def row(**k):
    return {
        "Mk": "FIAT", "Cn": "PANDA", "T": "312", "Va": "A", "Ve": "B", "Ft": "petrol", "Fm": "M",
        "ec": 999, "ep": 52, "m": 1000, "w": None, "at1": None, "co2": 100, "n": 1, **k,
    }


def store(rows=ROWS, today=TODAY):
    st = Store()
    eea.load(rows, st, 2025, today)
    return st


def read_csv(p):
    with open(p, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@pytest.fixture
def out(tmp_path):
    return tmp_path / "out"


@pytest.fixture
def v1(out):
    with store() as st:
        return export(st, out, "0.1.0", TODAY), out


def test_files_and_manifest(v1):
    m, out = v1
    assert set(m["files"]) == set(FILES)
    assert all((out / n).is_file() for n in FILES)
    assert (m["version"], m["previous"], m["license"], m["warnings"]) == ("0.1.0", None, "CC-BY-4.0", 0)
    assert m["counts"]["variants"] == 14 and m["counts"]["brands"] == 6 and m["counts"]["sources"] == 1
    assert json.loads((out / "manifest.json").read_text(encoding="utf-8")) == m


def test_hashes_match(v1):
    m, out = v1
    for n, h in m["files"].items():
        assert hashlib.sha256((out / n).read_bytes()).hexdigest() == h


def test_variants_csv(v1):
    _, out = v1
    rs = read_csv(out / "variants.csv")
    assert len(rs) == 14 and list(rs[0])[0] == "id"
    r = next(x for x in rs if x["id"] == "var_fiat-panda-312-pyd1b-s5g")
    assert (float(r["mass_kg"]), r["wheelbase_mm"], r["year_from"]) == (1045, "", "2025")


def test_provenance_csv(v1):
    _, out = v1
    rs = read_csv(out / "provenance.csv")
    assert list(rs[0]) == PC
    with store() as st:
        assert len(rs) == sum(len(p.evidence) for p in st.all_prov())
    assert {r["status"] for r in rs} == {"single_source"} and {r["source_id"] for r in rs} == {"eea-co2"}


def test_dataset_json(v1):
    m, out = v1
    d = json.loads((out / "dataset.json").read_text(encoding="utf-8"))
    assert (d["version"], d["generated"], d["license"]) == ("0.1.0", "2026-09-19", "CC-BY-4.0")
    assert {t: len(d[t]) for t in m["counts"]} == m["counts"]
    ids = [x["id"] for x in d["variants"]]
    assert ids == sorted(ids)
    assert d["sources"][0]["id"] == EEA.id and d["provenance"][0]["status"] == "single_source"


def test_legal_files_and_db_copy(v1):
    _, out = v1
    for f in ("LICENSE-DATA", "NOTICE"):
        assert (out / f).read_text(encoding="utf-8") == (LEGAL / f).read_text(encoding="utf-8")
    with Store(out / DB, ro=True) as r:
        assert len(r.find(Variant)) == 14


def test_first_release_changelog(v1):
    _, out = v1
    assert json.loads((out / "changelog.json").read_text(encoding="utf-8")) == {"from": None, "to": "0.1.0", "changes": None}
    md = (out / "CHANGELOG.md").read_text(encoding="utf-8")
    assert md.startswith("# openvehicle-data 0.1.0 (2026-09-19)") and "Initial release." in md and "- variants: 14" in md


def test_alias_column(tmp_path):
    with store([row(Cn="PANDA"), row(Cn="Panda"), row(Cn="panda")]) as st:
        export(st, tmp_path, "0.1.0", TODAY)
    assert read_csv(tmp_path / "models.csv")[0]["aliases"] == "Panda|panda"


@pytest.mark.parametrize("v", ["1.0", "v1.0.0", "1.0.0-rc", "", "1.0.0.0"])
def test_bad_version(out, v):
    with store() as st, pytest.raises(ValueError):
        export(st, out, v, TODAY)
    assert not out.exists()


def test_build_error_writes_nothing(out):
    with Store() as st:
        st.put(
            Brand(id="brand_a", name="A"), CarModel(id="model_a", brand_id="brand_a", name="A"),
            Generation(id="gen_a", model_id="model_a", name="I", year_from=2020, year_to=2020),
            Engine(id="eng_e", fuel="electric"),
            Variant(id="var_a", generation_id="gen_a", engine_id="eng_e", name="v", year_from=2020, year_to=2020, mass_kg=1500),
        )
        with pytest.raises(BuildError):
            export(st, out, "0.1.0", TODAY)
    assert not out.exists()


def test_warnings_counted(out):
    with store([row(m=100)]) as st:
        assert export(st, out, "0.1.0", TODAY)["warnings"] == 1


def test_default_today(out):
    with store() as st:
        export(st, out, "0.1.0")
    assert json.loads((out / "manifest.json").read_text(encoding="utf-8"))["generated"] == str(date.today())


def test_custom_legal_dir(out, tmp_path):
    lg = tmp_path / "legal"
    lg.mkdir()
    (lg / "LICENSE-DATA").write_text("L", encoding="utf-8")
    (lg / "NOTICE").write_text("N", encoding="utf-8")
    with store() as st:
        export(st, out, "0.1.0", TODAY, legal=lg)
    assert (out / "LICENSE-DATA").read_text(encoding="utf-8") == "L"


def test_changelog_between_versions(v1, tmp_path):
    _, d1 = v1
    b = [dict(r) for r in ROWS if r["Cn"] != "SANDERO"]
    next(r for r in b if r["Cn"] == "MODEL Y")["co2"] = 1
    b.append(row(Mk="ALFA ROMEO", Cn="GIULIA"))
    d2 = tmp_path / "out2"
    with store(b) as st:
        m = export(st, d2, "0.2.0", TODAY, prev=d1)
    assert m["previous"] == "0.1.0"
    ch = json.loads((d2 / "changelog.json").read_text(encoding="utf-8"))
    assert (ch["from"], ch["to"]) == ("0.1.0", "0.2.0")
    c = ch["changes"]
    assert c["variants"] == {
        "added": ["var_alfa-romeo-giulia-312-a-b"],
        "removed": ["var_dacia-sandero-djf-bev-mt6wa45m5d0b"],
        "changed": ["var_tesla-model-y-003-ys5ld-bhb3s5t3x"],
    }
    assert c["brands"] == {"added": ["brand_alfa-romeo"], "removed": ["brand_dacia"], "changed": []}
    assert "var_tesla-model-y-003-ys5ld-bhb3s5t3x:co2_wltp_g_km" in c["provenance"]["changed"]
    assert c["sources"] == {"added": [], "removed": [], "changed": []}
    md = (d2 / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "Changes since 0.1.0:" in md and "- variants: +1 -1 ~1" in md


def test_last_verified_is_not_a_change(v1, tmp_path):
    _, d1 = v1
    with store(today=date(2026, 10, 1)) as st:
        export(st, tmp_path / "out2", "0.1.1", date(2026, 10, 1), prev=d1)
    ch = json.loads((tmp_path / "out2" / "changelog.json").read_text(encoding="utf-8"))["changes"]
    assert all(not v for c in ch.values() for v in c.values())


def test_reexport_into_same_dir(v1):
    _, d = v1
    with store() as st:
        m = export(st, d, "0.1.1", TODAY, prev=d)
    assert m["previous"] == "0.1.0"
    assert json.loads((d / "manifest.json").read_text(encoding="utf-8"))["version"] == "0.1.1"


def test_deterministic_outputs(v1, tmp_path):
    m1, _ = v1
    with store() as st:
        m2 = export(st, tmp_path / "other", "0.1.0", TODAY)
    f1, f2 = dict(m1["files"]), dict(m2["files"])
    f1.pop(DB), f2.pop(DB)
    assert f1 == f2
