import argparse
import json
import tempfile
from pathlib import Path

from core.storage import Store
from pipeline.export import export
from pipeline.importers import eea, rdw
from pipeline.importers.eea_datasets import parse_years


def build(out, version, years, ms="IT", prev=None, client=None, today=None, check=True):
    with tempfile.TemporaryDirectory() as d:
        db = Path(d) / "build.db"
        stats = eea.run(db, years, ms, client, today)
        if check:
            stats["rdw"] = rdw.run(db, min(parse_years(years)), client, today)
        with Store(db) as st:
            return {"import": stats, "export": export(st, out, version, today, prev)}


def main(argv=None):
    a = argparse.ArgumentParser(prog="python -m pipeline.build")
    a.add_argument("--years", required=True, help="e.g. 2025, 2019-2025 or 2021,2023")
    a.add_argument("--version", required=True, help="dataset version X.Y.Z")
    a.add_argument("--out", required=True)
    a.add_argument("--country", default="IT")
    a.add_argument("--prev", help="folder of the previous export, for the changelog")
    a.add_argument("--skip-rdw", action="store_true", help="do not cross-check with the RDW data")
    n = a.parse_args(argv)
    r = build(n.out, n.version, n.years, n.country, n.prev, check=not n.skip_rdw)
    print(json.dumps({"import": r["import"], "counts": r["export"]["counts"], "warnings": r["export"]["warnings"]}, indent=1))


if __name__ == "__main__":
    main()
