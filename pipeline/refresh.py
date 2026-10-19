import argparse
import json
import re
import sys
from pathlib import Path


def nxt(tag):
    m = re.fullmatch(r"(?:data-)?v?(\d+)\.(\d+)\.(\d+)", tag)
    if not m:
        raise ValueError("tag must look like data-vX.Y.Z")
    a, b, c = map(int, m.groups())
    return f"{a}.{b}.{c + 1}"


def changed(path):
    d = json.loads(Path(path).read_text(encoding="utf-8"))["changes"]
    return any(c["added"] or c["removed"] or c["changed"] for c in d.values())


def guard(new, old, tol=0.05):
    a, b = (json.loads(Path(p).read_text(encoding="utf-8"))["counts"] for p in (new, old))
    return [f"{t}: {b[t]} -> {a.get(t, 0)}" for t in b if b[t] and a.get(t, 0) < b[t] * (1 - tol)]


def pin(dockerfile, manifest, tag):
    sha = json.loads(Path(manifest).read_text(encoding="utf-8"))["files"]["openvehicle-data.db"]
    p = Path(dockerfile)
    t = p.read_text(encoding="utf-8")
    t, n = re.subn(r"(ARG DATA_URL=\S*/releases/download/)[^/\s]+(/openvehicle-data\.db)", rf"\g<1>{tag}\g<2>", t)
    t, m = re.subn(r"(ARG DATA_SHA256=)[0-9a-f]{64}", rf"\g<1>{sha}", t)
    if n != 1 or m != 1:
        raise ValueError("DATA_URL / DATA_SHA256 not found in the Dockerfile")
    p.write_text(t, encoding="utf-8")


def main(argv=None):
    a = argparse.ArgumentParser(prog="python -m pipeline.refresh")
    s = a.add_subparsers(dest="cmd", required=True)
    s.add_parser("next").add_argument("tag")
    s.add_parser("changed").add_argument("path")
    g = s.add_parser("guard")
    g.add_argument("new")
    g.add_argument("old")
    g.add_argument("--tol", type=float, default=0.05)
    k = s.add_parser("pin")
    k.add_argument("dockerfile")
    k.add_argument("manifest")
    k.add_argument("tag")
    n = a.parse_args(argv)
    if n.cmd == "next":
        print(nxt(n.tag))
        return 0
    if n.cmd == "guard":
        bad = guard(n.new, n.old, n.tol)
        print(*bad or ["ok"], sep=chr(10))
        return 1 if bad else 0
    if n.cmd == "pin":
        pin(n.dockerfile, n.manifest, n.tag)
        return 0
    return 0 if changed(n.path) else 1


if __name__ == "__main__":
    sys.exit(main())
