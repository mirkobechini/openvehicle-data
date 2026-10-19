import re
from collections import Counter, defaultdict
from datetime import date

import httpx

from core.approval import base
from core.models import Brand, CarModel, Engine, Generation, Variant
from core.provenance import Evidence, FieldProvenance
from core.storage import Store
from pipeline import http
from pipeline.cli import cli
from pipeline.importers.corrections import norm
from pipeline.sources import RDW

URL = "https://opendata.rdw.nl/resource/m9d7-ebf2.json"
PAGE = "https://opendata.rdw.nl/Voertuigen/Open-Data-RDW-Gekentekende_voertuigen/m9d7-ebf2"
FUEL = "https://opendata.rdw.nl/resource/8ys7-d773.json"
UA = "openvehicle-data/0.0 (+https://github.com/mirkobechini/openvehicle-data)"
EURO = set("0123456")
STEP = 50000
BATCH = 400
KEY = ("merk", "type", "variant", "uitvoering")
CV = {"massa_rijklaar": ("mass_kg", float), "cilinderinhoud": ("displacement_cc", int), "wielbasis": ("wheelbase_mm", lambda v: int(v) * 10), "typegoedkeuringsnummer": ("type_approval", base), "aantal_zitplaatsen": ("seats", int), "toegestane_maximum_massa_voertuig": ("max_mass_kg", float)}
COLS = (*KEY, *CV)
NEW = ("type_approval", "seats", "max_mass_kg", "environmental_class")


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
            r = http.get(c, URL, params=q(since, STEP, len(rows)), headers={"Accept": "application/json", "User-Agent": UA})
            r.raise_for_status()
            p = r.json()
            rows += p
            if len(p) < STEP:
                return rows
    finally:
        if client is None:
            c.close()


def fetch_fuel(plates, client=None):
    c = client or httpx.Client(timeout=300)
    out = defaultdict(lambda: {"power": [], "euro": []})
    ok = [x for x in plates if re.fullmatch(r"[A-Z0-9]{1,8}", x or "")]
    try:
        for i in range(0, len(ok), BATCH):
            b = ",".join(f"'{x}'" for x in ok[i:i + BATCH])
            try:
                r = http.get(c, FUEL, params={"$select": "kenteken,nettomaximumvermogen,emissiecode_omschrijving", "$where": f"kenteken in({b})", "$limit": 5000}, headers={"Accept": "application/json", "User-Agent": UA})
                r.raise_for_status()
            except httpx.HTTPError as e:
                raise RuntimeError(f"RDW fuel request failed: {type(e).__name__}") from None
            for x in r.json():
                w = _num(x.get("nettomaximumvermogen"), float)
                if w is not None:
                    out[x["kenteken"]]["power"].append(w)
                if x.get("emissiecode_omschrijving") in EURO:
                    out[x["kenteken"]]["euro"].append(x["emissiecode_omschrijving"])
    finally:
        if client is None:
            c.close()
    return out


def fold_fuel(pl, fu):
    return {(norm(r["merk"] or ""), *(r.get(x) for x in KEY[1:])): {"power_kw": sorted(set(fu[r["k"]]["power"])), "environmental_class": f"Euro {max(fu[r['k']]['euro'])}" if fu[r["k"]]["euro"] else None} for r in pl if r["k"] in fu}


def _num(v, f):
    try:
        x = f(v)
    except (TypeError, ValueError):
        return None
    return x if x is not None and (isinstance(x, str) or x > 0) else None


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
    out, seen, hit, tot, nv = {}, set(), 0, 0, {}
    for v in st.find(Variant):
        tot += 1
        p = (v.type_code, v.variant_code, v.version_code)
        r = next((fo[(n, *p)] for n in sorted(bn[gb[v.generation_id]]) if (n, *p) in fo), None)
        if r is None:
            continue
        hit += 1
        for f in ("mass_kg", "wheelbase_mm"):
            if getattr(v, f) is not None:
                _add(st, v.id, f, r.get(f), today, seen, out)
        if en[v.engine_id].displacement_cc is not None:
            _add(st, v.engine_id, "displacement_cc", r.get("displacement_cc"), today, seen, out)
        if v.type_approval is not None:
            _add(st, v.id, "type_approval", r.get("type_approval"), today, seen, out)
        for f in NEW:
            if r.get(f) is not None and getattr(v, f) is None:
                nv[v.id] = nv.get(v.id, v).model_copy(update={f: r[f]})
                out[(v.id, f)] = FieldProvenance(entity_id=v.id, field=f, evidence=[Evidence(source_id=RDW.id, value=r[f], url=PAGE, retrieved=today)], last_verified=today)
        ep = en[v.engine_id].power_kw
        if r.get("power_kw") and ep is not None:
            _add(st, v.engine_id, "power_kw", min(r["power_kw"], key=lambda x: abs(x - ep)), today, seen, out)
    st.put(RDW, *nv.values())
    st.put_prov(*out.values())
    s = Counter(p.status.value for p in out.values())
    return {"variants": tot, "matched": hit, "fields": len(out), "confirmed": s["confirmed"], "conflicts": s["conflict"]}


def run(db, since, client=None, today=None):
    fo = fold(fetch(since, client))
    pl = fetch(since, client, query_plates)
    for k, v in fold_fuel(pl, fetch_fuel([x["k"] for x in pl], client)).items():
        fo.setdefault(k, {}).update(v)
    with Store(db) as st:
        return verify(st, fo, today)


def main(argv=None):
    cli("python -m pipeline.importers.rdw", [(("--db",), {"required": True}), (("--since",), {"type": int, "default": 2019})], lambda n: run(n.db, n.since), argv)


if __name__ == "__main__":
    main()
