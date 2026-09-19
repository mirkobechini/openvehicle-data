import csv
import hashlib
import json
import re
import shutil
from datetime import date
from pathlib import Path

from core.models import Brand, CarModel, Engine, Generation, Variant
from core.provenance import Source
from core.storage import Store
from pipeline.validation import ensure

LEGAL = Path(__file__).resolve().parents[1]
DB = "openvehicle-data.db"
LICENSE = "CC-BY-4.0"
TABLES = {
    "brands": Brand,
    "models": CarModel,
    "generations": Generation,
    "engines": Engine,
    "variants": Variant,
    "sources": Source,
}
FILES = [
    DB, *(f"{t}.csv" for t in [*TABLES, "provenance"]),
    "dataset.json", "LICENSE-DATA", "NOTICE", "changelog.json", "CHANGELOG.md",
]
PC = ["entity_id", "field", "status", "last_verified", "source_id", "value", "url", "retrieved"]


def _rows(st):
    d = {n: [o.model_dump(mode="json") for o in st.find(c)] for n, c in TABLES.items()}
    d["provenance"] = [p.model_dump(mode="json") for p in st.all_prov()]
    return d


def _flat(rows):
    return [
        {**{k: p[k] for k in PC[:4]}, **{k: e[k] for k in PC[4:]}}
        for p in rows
        for e in p["evidence"]
    ]


def _csv(path, rows, cols):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, cols)
        w.writeheader()
        for r in rows:
            w.writerow({k: "|".join(v) if isinstance(v, list) else v for k, v in r.items()})


def _key(t, r):
    return f"{r['entity_id']}:{r['field']}" if t == "provenance" else r["id"]


def _cmp(t, r):
    if t == "provenance":
        return [r["status"], [[e["source_id"], e["value"]] for e in r["evidence"]]]
    return r


def _diff(old, new):
    out = {}
    for t, rs in new.items():
        a = {_key(t, r): _cmp(t, r) for r in old[t]}
        b = {_key(t, r): _cmp(t, r) for r in rs}
        out[t] = {
            "added": sorted(b.keys() - a.keys()),
            "removed": sorted(a.keys() - b.keys()),
            "changed": sorted(k for k in a.keys() & b.keys() if a[k] != b[k]),
        }
    return out


def _md(v, today, pv, rows, ch):
    ls = [f"# openvehicle-data {v} ({today})", ""]
    if ch is None:
        ls.append("Initial release.")
        ls += [f"- {t}: {len(rs)}" for t, rs in rows.items()]
    else:
        ls.append(f"Changes since {pv}:")
        ls += [f"- {t}: +{len(c['added'])} -{len(c['removed'])} ~{len(c['changed'])}" for t, c in ch.items()]
    return "\n".join(ls) + "\n"


def _sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def export(st, out, version, today=None, prev=None, legal=LEGAL):
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("version must be X.Y.Z")
    warns = ensure(st)
    today = today or date.today()
    rows = _rows(st)
    pv = ch = None
    if prev is not None:
        pd = Path(prev)
        pv = json.loads((pd / "manifest.json").read_text(encoding="utf-8"))["version"]
        with Store(pd / DB, ro=True) as ps:
            ch = _diff(_rows(ps), rows)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    (out / DB).unlink(missing_ok=True)
    st.backup(out / DB)
    for t, c in TABLES.items():
        _csv(out / f"{t}.csv", rows[t], ["id", *(f for f in c.model_fields if f != "id")])
    _csv(out / "provenance.csv", _flat(rows["provenance"]), PC)
    head = {"version": version, "generated": str(today), "license": LICENSE}
    (out / "dataset.json").write_text(json.dumps({**head, **rows}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    for f in ("LICENSE-DATA", "NOTICE"):
        shutil.copy(Path(legal) / f, out / f)
    (out / "changelog.json").write_text(json.dumps({"from": pv, "to": version, "changes": ch}, ensure_ascii=False), encoding="utf-8")
    (out / "CHANGELOG.md").write_text(_md(version, today, pv, rows, ch), encoding="utf-8")
    man = {
        **head,
        "previous": pv,
        "counts": {t: len(rs) for t, rs in rows.items()},
        "warnings": len(warns),
        "files": {n: _sha(out / n) for n in sorted(FILES)},
    }
    (out / "manifest.json").write_text(json.dumps(man, indent=1), encoding="utf-8")
    return man
