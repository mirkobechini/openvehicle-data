import argparse
import re
from collections import Counter, defaultdict
from datetime import date

import httpx
from pydantic import ValidationError

from core.enums import Fuel
from core.ids import make_id, slug
from core.models import Brand, CarModel, Engine, Family, Generation, Variant
from core.provenance import Evidence, FieldProvenance
from core.storage import Store
from pipeline.importers.corrections import load_corrections, norm
from pipeline.importers.eea_datasets import COMBINED, DATASETS, parse_years
from pipeline.importers.families import family_of, load_family_rules
from pipeline.sources import EEA

URL = "https://discodata.eea.europa.eu/sql"
PAGE = "https://www.eea.europa.eu/data-and-maps/data/co2-cars-emission-22"
UA = "openvehicle-data/0.0 (+https://github.com/mirkobechini/openvehicle-data)"
VF = {"m": "mass_kg", "w": "wheelbase_mm", "at1": "track_width_mm", "co2": "co2_wltp_g_km"}
EF = {"ec": "displacement_cc", "ep": "power_kw"}
OPT = set(VF.values()) | set(EF.values())
FT = {
    "petrol": Fuel.PETROL,
    "diesel": Fuel.DIESEL,
    "lpg": Fuel.LPG,
    "ng": Fuel.CNG,
    "ng-biomethane": Fuel.CNG,
    "electric": Fuel.ELECTRIC,
    "hydrogen": Fuel.HYDROGEN,
}


def query(table, ms="IT", year=None, status=None):
    if not re.fullmatch(r"[A-Za-z0-9_]+", table) or not re.fullmatch(r"[A-Z]{2}", ms):
        raise ValueError("bad table or country")
    extra = ""
    if year is not None or status is not None:
        if not (type(year) is int and status in ("F", "P")):
            raise ValueError("bad year or status")
        extra = f" AND [Year]={year} AND Status='{status}'"
    return (
        "SELECT Mk, Cn, T, Va, Ve, Ft, Fm, [Ec (cm3)] AS ec, [Ep (KW)] AS ep, [M (kg)] AS m, "
        "[W (mm)] AS w, [At1 (mm)] AS at1, [Ewltp (g/km)] AS co2, COUNT(*) AS n "
        f"FROM [CO2Emission].[latest].[{table}] WHERE MS='{ms}' AND Ct='M1' AND Cr='M1'{extra} "
        "GROUP BY Mk, Cn, T, Va, Ve, Ft, Fm, [Ec (cm3)], [Ep (KW)], [M (kg)], [W (mm)], "
        "[At1 (mm)], [Ewltp (g/km)]"
    )


def fetch(table, ms="IT", client=None, year=None, status=None):
    c = client or httpx.Client(timeout=300)
    try:
        r = c.get(URL, params={"query": query(table, ms, year, status)}, headers={"Accept": "application/json", "User-Agent": UA})
    finally:
        if client is None:
            c.close()
    r.raise_for_status()
    d = r.json()
    if "errors" in d:
        raise RuntimeError(d["errors"])
    return d["results"]


def fetch_dataset(d, ms="IT", client=None):
    comb = d.table == COMBINED
    return fetch(d.table, ms, client, d.year if comb else None, d.status if comb else None)


def fuel(ft, fm):
    if fm == "P":
        return Fuel.PHEV
    if fm == "H":
        return Fuel.HYBRID
    return FT.get((ft or "").strip().lower(), Fuel.OTHER)


def _mk(cls, drops, **kw):
    try:
        return cls(**kw)
    except ValidationError as e:
        bad = {x["loc"][0] for x in e.errors()}
        if not bad <= OPT:
            raise
        drops.update(bad)
        return cls(**{**kw, **dict.fromkeys(bad)})


def _best(rs):
    return min(rs, key=lambda r: (-r["n"], *(1e18 if r[k] is None else r[k] for k in VF)))


def _key(s):
    return re.sub(r"(?<!\d)\.|\.(?!\d)", "", re.sub(r"[^A-Z0-9.]", "", s.upper()))


def _x(v):
    return "x" if v is None else v


def _strip(mk, cn):
    k = slug(mk).replace("-", "")
    ws = cn.split()
    for i in range(1, min(len(ws), 4)):
        if slug(" ".join(ws[:i])).replace("-", "") == k:
            return " ".join(ws[i:])
    return cn


def _pv(o, fs, urls, today, out):
    for f in fs:
        v = getattr(o, f)
        if v is not None:
            ev = Evidence(source_id=EEA.id, value=v, url=urls[f], retrieved=today)
            out.append(FieldProvenance(entity_id=o.id, field=f, evidence=[ev], last_verified=today))


def load(rows, st, year, today=None, corr=None, fam=None):
    return _load([{**r, "y": year} for r in rows], st, today, corr, fam, {year: PAGE})


def load_years(by_year, st, today=None, corr=None, fam=None):
    rows = [{**r, "y": y} for y in sorted(by_year) for r in by_year[y]]
    return _load(rows, st, today, corr, fam, {y: DATASETS[y].url for y in by_year})


def _load(rows, st, today, corr, fam, urls):
    today = today or date.today()
    corr = corr or load_corrections()
    fam = fam or load_family_rules()
    bmap = {norm(k): v for k, v in corr.brands.items()}
    ex = {(norm(x.brand), slug(x.model)) for x in corr.exclude_models}
    mmap = {(norm(x.brand), slug(x.model)): x.into for x in corr.merge_models}
    gr, bn, mn, skip, excl = defaultdict(list), defaultdict(set), defaultdict(set), 0, 0
    pre, cnt = [], Counter()
    for r in rows:
        mk0, raw = (r["Mk"] or "").strip(), (r["Cn"] or "").strip()
        if not (slug(mk0) and slug(raw)):
            skip += 1
            continue
        mk = bmap.get(norm(mk0), mk0)
        cn = _strip(mk, _strip(mk0, raw) if mk != mk0 else raw)
        if (norm(mk), slug(cn)) in ex:
            excl += 1
            continue
        cn0 = cn
        cn = mmap.get((norm(mk), slug(cn)), cn)
        pre.append((r, mk, mk0, raw, cn0, cn))
        cnt[(norm(mk), cn)] += r["n"]
    canon = {}
    for (b0, c0), _ in sorted(cnt.items(), key=lambda x: (-x[1], x[0][1])):
        canon.setdefault((b0, _key(c0)), c0)
    for r, mk, mk0, raw, cn0, cn in pre:
        cn = canon[(norm(mk), _key(cn))]
        b, m = make_id("brand", mk), make_id("model", mk, cn)
        bn[b].add((mk, mk0))
        mn[m].add((cn, raw, cn0))
        gr[(b, m, make_id("var", mk, cn, r["T"], r["Va"], r["Ve"]))].append(r)
    ms, gs, gy, es, eyr, vs, pv, drops, conf, mreg = {}, {}, {}, {}, {}, {}, [], Counter(), 0, Counter()
    for (b, m, vid), rs in sorted(gr.items()):
        by, wins, reg = {}, {}, 0
        for y in sorted({x["y"] for x in rs}):
            yr = [x for x in rs if x["y"] == y]
            ek = Counter()
            for x in yr:
                ek[(x["Ft"], x["Fm"], x["ec"], x["ep"])] += x["n"]
            wins[y] = max(sorted(ek, key=str), key=ek.get)
            kept = [x for x in yr if (x["Ft"], x["Fm"], x["ec"], x["ep"]) == wins[y]]
            conf += len(yr) - len(kept)
            reg += sum(x["n"] for x in kept)
            by[y] = _best(kept)
        ys = sorted(by)
        win = wins[ys[-1]]
        vals, src = {}, {}
        for y in reversed(ys):
            for c, f in VF.items():
                if f not in vals and by[y][c] is not None:
                    vals[f], src[f] = by[y][c], urls[y]
        r = by[ys[-1]]
        mreg[m] += reg
        ft, fm, ec, ep = win
        ms[m] = b
        gid = m.replace("model_", "gen_", 1) + "-observed"
        gs[gid] = m
        lo, hi = gy.get(gid, (ys[0], ys[-1]))
        gy[gid] = (min(lo, ys[0]), max(hi, ys[-1]))
        fl = fuel(ft, fm)
        eid = make_id("eng", fl.value, _x(ec), _x(ep))
        eyr[eid] = max(eyr.get(eid, 0), ys[-1])
        if eid not in es:
            es[eid] = _mk(Engine, drops, id=eid, fuel=fl, displacement_cc=ec, power_kw=ep)
        vs[vid] = _mk(
            Variant, drops, id=vid, generation_id=gid, engine_id=eid,
            name=" ".join(str(p).strip() for p in (r["T"], r["Va"], r["Ve"]) if p and str(p).strip()) or "unknown",
            year_from=ys[0], year_to=ys[-1], registrations=reg, **{f: vals.get(f) for f in VF.values()},
        )
        _pv(vs[vid], VF.values(), src, today, pv)
    for eid, e in es.items():
        _pv(e, EF.values(), dict.fromkeys(EF.values(), urls[eyr[eid]]), today, pv)
    bs = []
    for i, s in bn.items():
        nm = sorted(c for c, _ in s)[0]
        bs.append(Brand(id=i, name=nm, aliases=sorted({x for p in s for x in p} - {nm})))
    bname = {b.id: b.name for b in bs}
    cs, fms = [], {}
    for i, s in mn.items():
        nm = sorted(t[0] for t in s)[0]
        fn = family_of(fam, bname[ms[i]], nm)
        fid = make_id("family", bname[ms[i]], fn)
        cs.append(CarModel(id=i, brand_id=ms[i], name=nm, aliases=sorted({x for p in s for x in p} - {nm}), registrations=mreg[i], family_id=fid))
        f = fms.setdefault(fid, {"brand": ms[i], "name": fn, "n": 0, "reg": 0})
        f["n"] += 1
        f["reg"] += mreg[i]
    fl = [Family(id=i, brand_id=f["brand"], name=f["name"], model_count=f["n"], registrations=f["reg"]) for i, f in fms.items()]
    gl = [Generation(id=i, model_id=m, name="observed", year_from=gy[i][0], year_to=gy[i][1]) for i, m in gs.items()]
    st.put(EEA, *bs, *fl, *cs, *gl, *es.values(), *vs.values())
    st.put_prov(*pv)
    return {
        "years": sorted({r["y"] for r in rows}), "rows": len(rows), "skipped": skip, "excluded": excl, "conflicts": conf,
        "brands": len(bs), "families": len(fl), "models": len(cs), "engines": len(es), "variants": len(vs), "dropped": dict(drops),
    }


def run(db, years, ms="IT", client=None, today=None):
    ys = parse_years(years)
    by = {y: fetch_dataset(DATASETS[y], ms, client) for y in ys}
    with Store(db) as st:
        return load_years(by, st, today)


def main(argv=None):
    a = argparse.ArgumentParser(prog="python -m pipeline.importers.eea")
    a.add_argument("--years", required=True, help="e.g. 2025, 2019-2025 or 2021,2023")
    a.add_argument("--db", required=True)
    a.add_argument("--country", default="IT")
    n = a.parse_args(argv)
    print(run(n.db, n.years, n.country))


if __name__ == "__main__":
    main()
