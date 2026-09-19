import argparse
import json
import tempfile
from pathlib import Path

from core.storage import Store
from pipeline.export import export
from pipeline.importers import eea


def build(out, version, table, year, ms="IT", prev=None, client=None, today=None):
    with tempfile.TemporaryDirectory() as d:
        db = Path(d) / "build.db"
        stats = eea.run(db, table, year, ms, client, today)
        with Store(db) as st:
            return {"import": stats, "export": export(st, out, version, today, prev)}


def main(argv=None):
    a = argparse.ArgumentParser(prog="python -m pipeline.build")
    a.add_argument("--table", required=True, help="EEA table, e.g. co2cars_2025Pv31")
    a.add_argument("--year", type=int, required=True)
    a.add_argument("--version", required=True, help="dataset version X.Y.Z")
    a.add_argument("--out", required=True)
    a.add_argument("--country", default="IT")
    a.add_argument("--prev", help="folder of the previous export, for the changelog")
    n = a.parse_args(argv)
    r = build(n.out, n.version, n.table, n.year, n.country, n.prev)
    print(json.dumps({"import": r["import"], "counts": r["export"]["counts"], "warnings": r["export"]["warnings"]}, indent=1))


if __name__ == "__main__":
    main()
