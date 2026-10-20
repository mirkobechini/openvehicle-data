import argparse
import json
import tempfile
from pathlib import Path

from core.coverage import coverage
from core.storage import Store
from pipeline.export import export
from pipeline.importers import Ctx
from pipeline.importers import stages as STAGES


def build(out, version, years, ms="IT", prev=None, client=None, today=None, skip=frozenset(), stages=None):
    with tempfile.TemporaryDirectory() as d:
        db = Path(d) / "build.db"
        ctx = Ctx(years, ms, client, today, skip)
        first, *rest = [s for s in (stages or STAGES)() if s.enabled(ctx)]
        stats = first.run(db, ctx)
        for s in rest:
            stats[s.name] = s.run(db, ctx)
        with Store(db) as st:
            stats["coverage"] = coverage(st).overall.model_dump()
            return {"import": stats, "export": export(st, out, version, today, prev)}


def main(argv=None):
    a = argparse.ArgumentParser(prog="python -m pipeline.build")
    a.add_argument("--years", required=True, help="e.g. 2025, 2019-2025 or 2021,2023")
    a.add_argument("--version", required=True, help="dataset version X.Y.Z")
    a.add_argument("--out", required=True)
    a.add_argument("--country", default="IT")
    a.add_argument("--prev", help="folder of the previous export, for the changelog")
    a.add_argument("--skip", default="", help="comma-separated stage names to skip, e.g. rdw,traficom")
    n = a.parse_args(argv)
    r = build(n.out, n.version, n.years, n.country, n.prev, skip=frozenset(n.skip.split(",")) if n.skip else frozenset())
    print(json.dumps({"import": r["import"], "counts": r["export"]["counts"], "warnings": r["export"]["warnings"]}, indent=1))


if __name__ == "__main__":
    main()
