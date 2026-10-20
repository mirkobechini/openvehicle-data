import csv
import io
import zipfile
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
from pipeline.sources import TRAFICOM

URL = "https://opendata.traficom.fi/Content/Ajoneuvorekisteri.zip"
PAGE = "https://www.avoindata.fi/data/en/dataset/ajoneuvojen-avoin-data"
UA = "openvehicle-data/0.0 (+https://github.com/mirkobechini/openvehicle-data)"
ENCODING = "cp1252"
CAT = "M1"
CV = {
    "omamassa": ("mass_kg", float),
    "teknSuurSallKokmassa": ("max_mass_kg", float),
    "istumapaikkojenLkm": ("seats", int),
    "iskutilavuus": ("displacement_cc", int),
    "suurinNettoteho": ("power_kw", float),
}
NEW = ("seats", "max_mass_kg")


def fetch(client=None):
    c = client or httpx.Client(timeout=300)
    try:
        r = http.get(c, URL, headers={"User-Agent": UA})
        r.raise_for_status()
        return r.content
    finally:
        if client is None:
            c.close()


def rows(data):
    z = zipfile.ZipFile(io.BytesIO(data))
    f = io.TextIOWrapper(z.open(z.namelist()[0]), encoding=ENCODING, newline="")
    for r in csv.DictReader(f, delimiter=";"):
        if r.get("ajoneuvoluokka") == CAT:
            yield r


def _num(v, f):
    try:
        x = f(v)
    except (TypeError, ValueError):
        return None
    return x if x is not None and x > 0 else None


def fold(rows):
    c = defaultdict(lambda: defaultdict(Counter))
    for r in rows:
        ta = base(r.get("tyyppihyvaksyntanro") or "")
        if ta is None:
            continue
        k = (norm(r.get("merkkiSelvakielinen") or ""), ta, r.get("variantti") or "", r.get("versio") or "")
        for col, (f, cv) in CV.items():
            x = _num(r.get(col), cv)
            if x is not None:
                c[k][f][x] += 1
    return {k: {f: min(n, key=lambda x: (-n[x], x)) for f, n in fs.items()} for k, fs in c.items()}


def _add(st, eid, f, x, today, seen, out):
    if x is None or (eid, f, x) in seen:
        return
    seen.add((eid, f, x))
    p = next((p for p in st.prov(eid) if p.field == f), None)
    if p is None:
        return
    e = Evidence(source_id=TRAFICOM.id, value=x, url=PAGE, retrieved=today)
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
        if v.type_approval is None or not v.variant_code or not v.version_code:
            continue
        p = (v.type_approval, v.variant_code, v.version_code)
        r = next((fo[(n, *p)] for n in sorted(bn[gb[v.generation_id]]) if (n, *p) in fo), None)
        if r is None:
            continue
        hit += 1
        if v.mass_kg is not None:
            _add(st, v.id, "mass_kg", r.get("mass_kg"), today, seen, out)
        if en[v.engine_id].displacement_cc is not None:
            _add(st, v.engine_id, "displacement_cc", r.get("displacement_cc"), today, seen, out)
        if en[v.engine_id].power_kw is not None:
            _add(st, v.engine_id, "power_kw", r.get("power_kw"), today, seen, out)
        for f in NEW:
            if r.get(f) is not None and getattr(v, f) is None:
                nv[v.id] = nv.get(v.id, v).model_copy(update={f: r[f]})
                out[(v.id, f)] = FieldProvenance(entity_id=v.id, field=f, evidence=[Evidence(source_id=TRAFICOM.id, value=r[f], url=PAGE, retrieved=today)], last_verified=today)
    st.put(TRAFICOM, *nv.values())
    st.put_prov(*out.values())
    s = Counter(p.status.value for p in out.values())
    return {"variants": tot, "matched": hit, "fields": len(out), "confirmed": s["confirmed"], "conflicts": s["conflict"]}


def run(db, client=None, today=None):
    fo = fold(rows(fetch(client)))
    with Store(db) as st:
        return verify(st, fo, today)


def main(argv=None):
    cli("python -m pipeline.importers.traficom", [(("--db",), {"required": True})], lambda n: run(n.db), argv)


if __name__ == "__main__":
    main()
