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
