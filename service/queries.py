import difflib
from datetime import date
from typing import Generic, TypeVar

from pydantic import BaseModel

from core.approval import base
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
    provenance: list[ProvenanceOut]


class Found(BaseModel):
    brands: list[Brand]
    families: list[Family]
    models: list[CarModel]
    did_you_mean: list[str]


class Meta(BaseModel):
    version: str
    generated: str | None
    software_version: str
    license: str
    attribution: str
    counts: dict[str, int]
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


def _ix(cur, ids):
    ids = set(ids)
    return ids if cur is None else cur & ids


def variants_page(st, lo, q=None, model_id=None, generation_id=None, engine_id=None, fuel=None, sort="id", min_reg=None, brand_id=None, family_id=None, year=None, type_approval=None):
    for c, i in ((Brand, brand_id), (Family, family_id), (CarModel, model_id), (Generation, generation_id), (Engine, engine_id)):
        need(st, c, i)
    w, g, e = {}, None, None
    if family_id:
        ms = [x.id for x in st.find(CarModel, family_id=family_id)]
        g = _ix(g, (x.id for x in st.find(Generation, model_id=ms)))
    if brand_id:
        ms = [x.id for x in st.find(CarModel, brand_id=brand_id)]
        g = _ix(g, (x.id for x in st.find(Generation, model_id=ms)))
    if model_id:
        g = _ix(g, (x.id for x in st.find(Generation, model_id=model_id)))
    if generation_id:
        g = _ix(g, [generation_id])
    if fuel:
        e = _ix(e, (x.id for x in st.find(Engine, fuel=fuel)))
    if engine_id:
        e = _ix(e, [engine_id])
    if g is not None:
        w["generation_id"] = sorted(g)
    if e is not None:
        w["engine_id"] = sorted(e)
    if type_approval is not None:
        w["type_approval"] = base(type_approval)
    if year is not None:
        w["year_from__lte"] = w["year_to__gte"] = year
    return page(st, Variant, lo, q, sort, min_reg, **w)


def variant_detail(st, i):
    v = one(st, Variant, i)
    e = st.get(Engine, v.engine_id)
    ps = [ProvenanceOut(**p.model_dump()) for p in (*st.prov(v.id), *st.prov(e.id))]
    return VariantDetail(**v.model_dump(), engine=e, provenance=ps)


def _suggest(st, q):
    bs = st.find(Brand)
    names = {b.name for b in bs} | {a for b in bs for a in b.aliases}
    names |= {n for m in st.find(CarModel) for n in (m.name, *m.aliases)}
    names |= {f.name for f in st.find(Family)}
    return _near(q, names, 5, 0.7)


def search(st, q):
    bs, fs, ms = st.find(Brand, q=q, limit=10), st.find(Family, q=q, limit=10), st.find(CarModel, q=q, limit=10)
    return Found(brands=bs, families=fs, models=ms, did_you_mean=[] if bs or fs or ms else _suggest(st, q))


def meta(st, version):
    cs = {c.__name__: st.count(c) for c in (Brand, Family, CarModel, Generation, Engine, Variant, Source)}
    return Meta(version=st.get_meta("version") or "unknown", generated=st.get_meta("generated"), software_version=version, license="CC-BY-4.0", attribution=ATTR, counts=cs, sources=st.find(Source))
