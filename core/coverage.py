from pydantic import BaseModel

from core.models import Brand

VF = ("mass_kg", "wheelbase_mm", "track_width_mm", "co2_wltp_g_km", "type_approval", "type_code", "variant_code", "version_code")
EF = ("displacement_cc", "power_kw")


class FieldCov(BaseModel):
    variants: int
    share: float
    weighted: float | None


class Cov(BaseModel):
    variants: int
    registrations: int
    fields: dict[str, FieldCov]


class BrandCov(Cov):
    brand_id: str
    name: str


class Coverage(BaseModel):
    overall: Cov
    brands: list[BrandCov]


def _cov(n, reg, cn, cr):
    return {"variants": n, "registrations": reg, "fields": {f: {"variants": cn[f], "share": round(cn[f] / n, 4), "weighted": round(cr[f] / reg, 4) if reg else None} for f in cn}}


def coverage(st, brand_id=None):
    rows = st.coverage(VF, EF, brand_id)
    names = {b.id: b.name for b in st.find(Brand)}
    bs = [BrandCov(brand_id=r["brand_id"], name=names[r["brand_id"]], **_cov(r["n"], r["reg"], r["cn"], r["cr"])) for r in rows]
    n, reg = sum(b.variants for b in bs), sum(b.registrations for b in bs)
    cn = {f: sum(b.fields[f].variants for b in bs) for f in (*VF, *EF)}
    cr = {f: sum(r["cr"][f] for r in rows) for f in cn}
    return Coverage(overall=Cov(**_cov(n, reg, cn, cr)) if n else Cov(variants=0, registrations=0, fields={}), brands=bs)
