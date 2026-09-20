import argparse
import re
from collections import Counter, defaultdict
from datetime import date

import httpx

from core.models import Brand, CarModel, Engine, Generation, Variant
from core.provenance import Evidence, FieldProvenance
from core.storage import Store
from pipeline.importers.corrections import norm
from pipeline.sources import RDW

URL = "https://opendata.rdw.nl/resource/m9d7-ebf2.json"
PAGE = "https://opendata.rdw.nl/Voertuigen/Open-Data-RDW-Gekentekende_voertuigen/m9d7-ebf2"
FUEL = "https://opendata.rdw.nl/resource/8ys7-d773.json"
UA = "openvehicle-data/0.0 (+https://github.com/mirkobechini/openvehicle-data)"
STEP = 50000
BATCH = 400
KEY = ("merk", "type", "variant", "uitvoering")
CV = {"massa_rijklaar": ("mass_kg", float), "cilinderinhoud": ("displacement_cc", int), "wielbasis": ("wheelbase_mm", lambda v: int(v) * 10)}
COLS = (*KEY, *CV)


def _q(since, cols, sel, limit, offset):
    if not (type(since) is int and 1900 <= since <= 2100):
        raise ValueError("bad year")
    return {
        "$select": ",".join(cols) + "," + sel,
        "$where": f"europese_voertuigcategorie='M1' AND voertuigsoort='Personenauto' AND datum_eerste_toelating>='{since}0101'",
        "$group": ",".join(cols),
        "$order": ",".join(cols),
        "$limit": limit,
        "$offset": offset,
    }


def query(since, limit=STEP, offset=0):
    return _q(since, COLS, "count(*) as n", limit, offset)


def query_plates(since, limit=STEP, offset=0):
    return _q(since, KEY, "min(kenteken) as k", limit, offset)


def fetch(since, client=None, q=query):
    c = client or httpx.Client(timeout=300)
    rows = []
    try:
        while True:
            r = c.get(URL, params=q(since, STEP, len(rows)), headers={"Accept": "application/json", "User-Agent": UA})
            r.raise_for_status()
            p = r.json()
            rows += p
            if len(p) < STEP:
                return rows
    finally:
        if client is None:
            c.close()


def fetch_power(plates, client=None):
    c = client or httpx.Client(timeout=300)
    out = defaultdict(list)
    ok = [x for x in plates if re.fullmatch(r"[A-Z0-9]{1,8}", x or "")]
    try:
        for i in range(0, len(ok), BATCH):
            b = ",".join(f"'{x}'" for x in ok[i:i + BATCH])
            try:
                r = c.get(FUEL, params={"$select": "kenteken,nettomaximumvermogen", "$where": f"kenteken in({b})", "$limit": 5000}, headers={"Accept": "application/json", "User-Agent": UA})
                r.raise_for_status()
            except httpx.HTTPError as e:
                raise RuntimeError(f"RDW fuel request failed: {type(e).__name__}") from None
            for x in r.json():
                w = _num(x.get("nettomaximumvermogen"), float)
                if w is not None:
                    out[x["kenteken"]].append(w)
    finally:
        if client is None:
            c.close()
    return out


def fold_power(pl, pw):
    return {(norm(r["merk"] or ""), *(r.get(x) for x in KEY[1:])): sorted(set(pw[r["k"]])) for r in pl if r["k"] in pw}


def _num(v, f):
    try:
        x = f(v)
    except (TypeError, ValueError):
        return None
    return x if x > 0 else None


def fold(rows):
    c = defaultdict(lambda: defaultdict(Counter))
    for r in rows:
        k = (norm(r.get("merk") or ""), *(r.get(x) for x in KEY[1:]))
        for col, (f, cv) in CV.items():
            x = _num(r.get(col), cv)
            if x is not None:
                c[k][f][x] += int(r["n"])
    return {k: {f: min(n, key=lambda x: (-n[x], x)) for f, n in fs.items()} for k, fs in c.items()}


def _add(st, eid, f, x, today, seen, out):
    if x is None or (eid, f, x) in seen:
        return
    seen.add((eid, f, x))
    p = next((p for p in st.prov(eid) if p.field == f), None)
    if p is None:
        return
    e = Evidence(source_id=RDW.id, value=x, url=PAGE, retrieved=today)
    out[(eid, f)] = FieldProvenance(entity_id=eid, field=f, evidence=[*(out[(eid, f)] if (eid, f) in out else p).evidence, e], last_verified=today)


def verify(st, fo, today=None):
    today = today or date.today()
    bn = {b.id: {norm(n) for n in (b.name, *b.aliases)} for b in st.find(Brand)}
    mb = {m.id: m.brand_id for m in st.find(CarModel)}
    gb = {g.id: mb[g.model_id] for g in st.find(Generation)}
    en = {e.id: e for e in st.find(Engine)}
    out, seen, hit, tot = {}, set(), 0, 0
    for v in st.find(Variant):
        tot += 1
        p = v.name.split(" ")
        r = next((fo[(n, *p)] for n in sorted(bn[gb[v.generation_id]]) if len(p) == 3 and (n, *p) in fo), None)
        if r is None:
            continue
        hit += 1
        for f in ("mass_kg", "wheelbase_mm"):
            if getattr(v, f) is not None:
                _add(st, v.id, f, r.get(f), today, seen, out)
        if en[v.engine_id].displacement_cc is not None:
            _add(st, v.engine_id, "displacement_cc", r.get("displacement_cc"), today, seen, out)
        ep = en[v.engine_id].power_kw
        if r.get("power_kw") and ep is not None:
            _add(st, v.engine_id, "power_kw", min(r["power_kw"], key=lambda x: abs(x - ep)), today, seen, out)
    st.put(RDW)
    st.put_prov(*out.values())
    s = Counter(p.status.value for p in out.values())
    return {"variants": tot, "matched": hit, "fields": len(out), "confirmed": s["confirmed"], "conflicts": s["conflict"]}


def run(db, since, client=None, today=None):
    fo = fold(fetch(since, client))
    with Store(db) as st:
        return verify(st, fo, today)


def main(argv=None):
    a = argparse.ArgumentParser(prog="python -m pipeline.importers.rdw")
    a.add_argument("--db", required=True)
    a.add_argument("--since", type=int, default=2019)
    n = a.parse_args(argv)
    print(run(n.db, n.since))


if __name__ == "__main__":
    main()
