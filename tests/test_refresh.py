import json

import pytest

from pipeline import refresh as rf


def log(tmp_path, **k):
    t = {"added": [], "removed": [], "changed": []}
    p = tmp_path / "changelog.json"
    p.write_text(json.dumps({"from": "0.1.0", "to": "0.1.1", "changes": {"brands": {**t, **k}, "variants": t}}), encoding="utf-8")
    return p


@pytest.mark.parametrize("tag,v", [("data-v0.7.0", "0.7.1"), ("v1.2.9", "1.2.10"), ("0.9.3", "0.9.4")])
def test_next(tag, v):
    assert rf.nxt(tag) == v


@pytest.mark.parametrize("tag", ["data-v1.0", "latest", "data-v1.0.0-rc1", ""])
def test_next_rejects_odd_tags(tag):
    with pytest.raises(ValueError):
        rf.nxt(tag)


def test_unchanged(tmp_path):
    assert not rf.changed(log(tmp_path))


@pytest.mark.parametrize("k", ["added", "removed", "changed"])
def test_changed(tmp_path, k):
    assert rf.changed(log(tmp_path, **{k: ["brand_x"]}))


def test_main_next(capsys):
    assert rf.main(["next", "data-v0.7.0"]) == 0
    assert capsys.readouterr().out == "0.7.1\n"


def test_main_changed_exit_codes(tmp_path):
    assert rf.main(["changed", str(log(tmp_path, added=["x"]))]) == 0
    assert rf.main(["changed", str(log(tmp_path))]) == 1


def man(tmp_path, name, counts, sha="a" * 64):
    p = tmp_path / name
    p.write_text(json.dumps({"counts": counts, "files": {"openvehicle-data.db": sha}}), encoding="utf-8")
    return p


def test_guard_accepts_small_changes_and_growth(tmp_path):
    old = man(tmp_path, "o.json", {"variants": 1000, "brands": 90, "empty": 0})
    assert rf.guard(man(tmp_path, "a.json", {"variants": 960, "brands": 95, "empty": 0}), old) == []


def test_guard_flags_a_table_that_shrinks_or_vanishes(tmp_path):
    old = man(tmp_path, "o.json", {"variants": 1000, "brands": 90, "models": 10})
    assert rf.guard(man(tmp_path, "a.json", {"variants": 900, "brands": 90}), old) == ["variants: 1000 -> 900", "models: 10 -> 0"]
    assert rf.guard(man(tmp_path, "b.json", {"variants": 900, "brands": 90, "models": 10}), old, tol=0.2) == []


def test_main_guard_exit_codes(tmp_path, capsys):
    old = man(tmp_path, "o.json", {"variants": 100})
    assert rf.main(["guard", str(man(tmp_path, "a.json", {"variants": 99})), str(old)]) == 0
    assert capsys.readouterr().out == "ok\n"
    assert rf.main(["guard", str(man(tmp_path, "b.json", {"variants": 10})), str(old), "--tol", "0.1"]) == 1
    assert capsys.readouterr().out == "variants: 100 -> 10\n"


DF = "FROM x\n\nARG DATA_URL=https://github.com/o/r/releases/download/data-v0.9.0/openvehicle-data.db\nARG DATA_SHA256=" + "0" * 64 + "\nRUN y\n"


def test_pin_rewrites_the_release_and_the_checksum(tmp_path):
    d = tmp_path / "Dockerfile"
    d.write_text(DF, encoding="utf-8")
    rf.pin(d, man(tmp_path, "m.json", {}, "b" * 64), "data-v0.10.1")
    t = d.read_text(encoding="utf-8")
    assert "download/data-v0.10.1/openvehicle-data.db" in t and f"ARG DATA_SHA256={'b' * 64}" in t
    assert t.startswith("FROM x") and t.endswith("RUN y\n") and "data-v0.9.0" not in t


@pytest.mark.parametrize("bad", ["FROM x\n", DF.replace("ARG DATA_SHA256=" + "0" * 64, "ARG DATA_SHA256=short"), DF.replace("download/", "dl/")])
def test_pin_refuses_a_dockerfile_it_does_not_understand(tmp_path, bad):
    d = tmp_path / "Dockerfile"
    d.write_text(bad, encoding="utf-8")
    with pytest.raises(ValueError):
        rf.pin(d, man(tmp_path, "m.json", {}), "data-v1.0.0")


def test_main_pin(tmp_path):
    d = tmp_path / "Dockerfile"
    d.write_text(DF, encoding="utf-8")
    assert rf.main(["pin", str(d), str(man(tmp_path, "m.json", {}, "c" * 64)), "data-v0.10.1"]) == 0
    assert "c" * 64 in d.read_text(encoding="utf-8")
