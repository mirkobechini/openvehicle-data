import argparse
import re
from collections import Counter, defaultdict
from datetime import date

import httpx
from pydantic import ValidationError

from core.enums import Fuel
from core.ids import make_id, slug
from core.models import Brand, CarModel, Engine, Generation, Variant
from core.provenance import Evidence, FieldProvenance
from core.storage import Store
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


def query(table, ms="IT"):
    if not re.fullmatch(r"[A-Za-z0-9_]+", table) or not re.fullmatch(r"[A-Z]{2}", ms):
        raise ValueError("bad table or country")
    return (
        "SELECT Mk, Cn, T, Va, Ve, Ft, Fm, [Ec (cm3)] AS ec, [Ep (KW)] AS ep, [M (kg)] AS m, "
        "[W (mm)] AS w, [At1 (mm)] AS at1, [Ewltp (g/km)] AS co2, COUNT(*) AS n "
        f"FROM [CO2Emission].[latest].[{table}] WHERE MS='{ms}' AND Ct='M1' AND Cr='M1' "
        "GROUP BY Mk, Cn, T, Va, Ve, Ft, Fm, [Ec (cm3)], [Ep (KW)], [M (kg)], [W (mm)], "
        "[At1 (mm)], [Ewltp (g/km)]"
    )


def fetch(table, ms="IT", client=None):
    with client or httpx.Client(timeout=300) as c:
        r = c.get(URL, params={"query": query(table, ms)}, headers={"Accept": "application/json", "User-Agent": UA})
    r.raise_for_status()
    d = r.json()
    if "errors" in d:
        raise RuntimeError(d["errors"])
    return d["results"]


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


def _x(v):
    return "x" if v is None else v


def _strip(mk, cn):
    k = slug(mk).replace("-", "")
    ws = cn.split()
    for i in range(1, min(len(ws), 4)):
        if slug(" ".join(ws[:i])).replace("-", "") == k:
            return " ".join(ws[i:])
    return cn


def _pv(o, fs, today, out):
    for f in fs:
        v = getattr(o, f)
        if v is not None:
            ev = Evidence(source_id=EEA.id, value=v, url=PAGE, retrieved=today)
            out.append(FieldProvenance(entity_id=o.id, field=f, evidence=[ev], last_verified=today))


def load(rows, st, year, today=None):
    today = today or date.today()
    gr, bn, mn, skip = defaultdict(list), defaultdict(set), defaultdict(set), 0
    for r in rows:
        mk, raw = (r["Mk"] or "").strip(), (r["Cn"] or "").strip()
        if not (slug(mk) and slug(raw)):
            skip += 1
            continue
        cn = _strip(mk, raw)
        b, m = make_id("brand", mk), make_id("model", mk, cn)
        bn[b].add(mk)
        mn[m].add((cn, raw))
        gr[(b, m, make_id("var", mk, cn, r["T"], r["Va"], r["Ve"]))].append(r)
    ms, gs, es, vs, pv, drops, conf, mreg = {}, {}, {}, {}, [], Counter(), 0, Counter()
    for (b, m, vid), rs in sorted(gr.items()):
        ek = Counter()
        for r in rs:
            ek[(r["Ft"], r["Fm"], r["ec"], r["ep"])] += r["n"]
        win = max(sorted(ek, key=str), key=ek.get)
        keep = [r for r in rs if (r["Ft"], r["Fm"], r["ec"], r["ep"]) == win]
        conf += len(rs) - len(keep)
        r = _best(keep)
        reg = sum(x["n"] for x in keep)
        mreg[m] += reg
        ft, fm, ec, ep = win
        ms[m] = b
        gid = m.replace("model_", "gen_", 1) + "-observed"
        gs[gid] = m
        fl = fuel(ft, fm)
        eid = make_id("eng", fl.value, _x(ec), _x(ep))
        if eid not in es:
            es[eid] = _mk(Engine, drops, id=eid, fuel=fl, displacement_cc=ec, power_kw=ep)
            _pv(es[eid], EF.values(), today, pv)
        vs[vid] = _mk(
            Variant, drops, id=vid, generation_id=gid, engine_id=eid,
            name=" ".join(str(p).strip() for p in (r["T"], r["Va"], r["Ve"]) if p and str(p).strip()) or "unknown",
            year_from=year, year_to=year, registrations=reg, **{f: r[c] for c, f in VF.items()},
        )
        _pv(vs[vid], VF.values(), today, pv)
    bs = [Brand(id=i, name=sorted(s)[0], aliases=sorted(s)[1:]) for i, s in bn.items()]
    cs = []
    for i, s in mn.items():
        nm = sorted(c for c, _ in s)[0]
        cs.append(CarModel(id=i, brand_id=ms[i], name=nm, aliases=sorted({x for p in s for x in p} - {nm}), registrations=mreg[i]))
    gl = [Generation(id=i, model_id=m, name="observed", year_from=year, year_to=year) for i, m in gs.items()]
    st.put(EEA, *bs, *cs, *gl, *es.values(), *vs.values())
    st.put_prov(*pv)
    return {
        "rows": len(rows), "skipped": skip, "conflicts": conf, "brands": len(bs), "models": len(cs),
        "engines": len(es), "variants": len(vs), "dropped": dict(drops),
    }


def run(db, table, year, ms="IT", client=None, today=None):
    rows = fetch(table, ms, client)
    with Store(db) as st:
        return load(rows, st, year, today)


def main(argv=None):
    a = argparse.ArgumentParser(prog="python -m pipeline.importers.eea")
    a.add_argument("--table", required=True)
    a.add_argument("--year", type=int, required=True)
    a.add_argument("--db", required=True)
    a.add_argument("--country", default="IT")
    n = a.parse_args(argv)
    print(run(n.db, n.table, n.year, n.country))


if __name__ == "__main__":
    main()
