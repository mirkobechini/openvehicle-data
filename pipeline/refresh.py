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


def main(argv=None):
    a = argparse.ArgumentParser(prog="python -m pipeline.refresh")
    s = a.add_subparsers(dest="cmd", required=True)
    s.add_parser("next").add_argument("tag")
    s.add_parser("changed").add_argument("path")
    n = a.parse_args(argv)
    if n.cmd == "next":
        print(nxt(n.tag))
        return 0
    return 0 if changed(n.path) else 1


if __name__ == "__main__":
    sys.exit(main())
