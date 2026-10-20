import difflib
from datetime import date
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, Field

from core.approval import base
from core.coverage import Cov, coverage
from core.enums import Fuel
from core.models import Base, Brand, CarModel, Engine, Family, Generation, Variant
from core.provenance import Evidence, Source, Status

T = TypeVar("T")
ATTR = "Data from openvehicle-data (https://github.com/mirkobechini/openvehicle-data), CC BY 4.0. See NOTICE for upstream sources."


class Page(BaseModel, Generic[T]):
    total: int
    limit: int
    offset: int
    count: int
    has_more: bool
    next_offset: int | None
    items: list[T]


class ProvenanceOut(Base):
    entity_id: str
    field: str
    evidence: list[Evidence]
    last_verified: date
    status: Status


class VariantDetail(Variant):
    engine: Engine
    brand: Brand
    model: CarModel
    provenance: list[ProvenanceOut]


class Found(BaseModel):
    brands: list[Brand]
    families: list[Family]
    models: list[CarModel]
    did_you_mean: list[str]


class Meta(BaseModel):
    version: str
    schema_version: int | None
    generated: str | None
    software_version: str
    license: str
    attribution: str
    counts: dict[str, int]
    coverage: Cov
    sources: list[Source]


SORTS = {"id": "id", "registrations": "-registrations"}


def page(st, cls, lo, q=None, sort="id", min_reg=None, **w):
    if min_reg is not None:
        w["registrations__gte"] = min_reg
    total = st.count(cls, q=q, **w)
    items = st.find(cls, q=q, limit=lo[0], offset=lo[1], sort=SORTS[sort], **w)
    end = lo[1] + len(items)
    more = end < total
    return {
        "total": total,
        "limit": lo[0],
        "offset": lo[1],
        "count": len(items),
        "has_more": more,
        "next_offset": end if more else None,
        "items": items,
    }


def _near(x, cands, n=3, cutoff=0.75):
    low = {c.lower(): c for c in cands}
    return [low[k] for k in difflib.get_close_matches(x.lower(), list(low), n=n, cutoff=cutoff)]


def _missing(cls, i, cands):
    near = _near(i, cands)
    return LookupError(f"{cls.__name__} {i} not found" + (f". Did you mean: {', '.join(near)}?" if near else ""))


def one(st, cls, i):
    o = st.get(cls, i)
    if o is None:
        raise _missing(cls, i, st.ids(cls))
    return o


def need(st, cls, i):
    if i and st.get(cls, i) is None:
        raise _missing(cls, i, st.ids(cls))


def models_page(st, lo, q=None, brand_id=None, sort="id", min_reg=None, family_id=None):
    need(st, Brand, brand_id)
    need(st, Family, family_id)
    w = {k: v for k, v in (("brand_id", brand_id), ("family_id", family_id)) if v}
    return page(st, CarModel, lo, q, sort, min_reg, **w)


def families_page(st, lo, q=None, brand_id=None, sort="id", min_reg=None):
    need(st, Brand, brand_id)
    return page(st, Family, lo, q, sort, min_reg, **({"brand_id": brand_id} if brand_id else {}))


def generations_page(st, lo, model_id=None):
    need(st, CarModel, model_id)
    return page(st, Generation, lo, **({"model_id": model_id} if model_id else {}))


class VariantQuery(BaseModel):
    q: str | None = Field(None, min_length=1, max_length=100, description="Case-insensitive search in name and aliases")
    brand_id: str | None = None
    family_id: str | None = None
    model_id: str | None = None
    generation_id: str | None = None
    engine_id: str | None = None
    fuel: Fuel | None = None
    sort: Literal["id", "registrations"] = Field("id", description="'registrations' lists the most registered first")
    min_registrations: int | None = Field(None, ge=0, description="Only entries with at least this many registrations")
    year: int | None = Field(None, ge=1900, le=2100, description="Only variants registered in this year")
    type_approval: str | None = Field(None, pattern=r"^\s*[eE]\d{1,3}\*[^*\s]+\*[^*\s]+(\*[^*\s]+)?\s*$", description="EU type-approval number as on the registration document, e.g. e3*2007/46*0064*05 or without the last part")
    type_code: str | None = Field(None, min_length=1, max_length=40, description="Vehicle type, first part of field D.2 of the registration document, e.g. 312")
    variant_code: str | None = Field(None, min_length=1, max_length=40, description="Variant, second part of D.2, e.g. PYD1B")
    version_code: str | None = Field(None, min_length=1, max_length=40, description="Version, third part of D.2, e.g. AA4")


def variants_page(st, lo, f):
    for c, i in ((Brand, f.brand_id), (Family, f.family_id), (CarModel, f.model_id), (Generation, f.generation_id), (Engine, f.engine_id)):
        need(st, c, i)
    gs = [{x.id for x in st.find(Generation, model_id=[m.id for m in st.find(CarModel, **{k: v})])} for k, v in (("family_id", f.family_id), ("brand_id", f.brand_id)) if v]
    if f.model_id:
        gs.append({x.id for x in st.find(Generation, model_id=f.model_id)})
    if f.generation_id:
        gs.append({f.generation_id})
    es = []
    if f.fuel:
        es.append({x.id for x in st.find(Engine, fuel=f.fuel)})
    if f.engine_id:
        es.append({f.engine_id})
    w = {k: sorted(set.intersection(*ss)) for k, ss in (("generation_id", gs), ("engine_id", es)) if ss}
    w.update({k: v.strip() for k in ("type_code", "variant_code", "version_code") if (v := getattr(f, k)) is not None})
    if f.type_approval is not None:
        w["type_approval"] = base(f.type_approval)
    if f.year is not None:
        w["years__has"] = f.year
    return page(st, Variant, lo, f.q, f.sort, f.min_registrations, **w)


def variant_detail(st, i):
    v = one(st, Variant, i)
    e = st.get(Engine, v.engine_id)
    m = st.get(CarModel, st.get(Generation, v.generation_id).model_id)
    ps = [ProvenanceOut(**p.model_dump()) for p in (*st.prov(v.id), *st.prov(e.id))]
    return VariantDetail(**v.model_dump(), engine=e, brand=st.get(Brand, m.brand_id), model=m, provenance=ps)


def _suggest(st, q):
    bs = st.find(Brand)
    names = {b.name for b in bs} | {a for b in bs for a in b.aliases}
    names |= {n for m in st.find(CarModel) for n in (m.name, *m.aliases)}
    names |= {f.name for f in st.find(Family)}
    return _near(q, names, 5, 0.7)


def search(st, q):
    bs, fs, ms = st.find(Brand, q=q, limit=10), st.find(Family, q=q, limit=10), st.find(CarModel, q=q, limit=10)
    return Found(brands=bs, families=fs, models=ms, did_you_mean=[] if bs or fs or ms else _suggest(st, q))


def coverage_of(st, brand_id=None):
    need(st, Brand, brand_id)
    return coverage(st, brand_id)


def meta(st, version):
    cs = {c.__name__: st.count(c) for c in (Brand, Family, CarModel, Generation, Engine, Variant, Source)}
    return Meta(version=st.get_meta("version") or "unknown", schema_version=int(st.get_meta("schema_version") or 0) or None, generated=st.get_meta("generated"), software_version=version, license="CC-BY-4.0", attribution=ATTR, counts=cs, coverage=coverage(st).overall, sources=st.find(Source))
