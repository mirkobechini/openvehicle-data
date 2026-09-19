from typing import Generic, TypeVar

from pydantic import BaseModel

from core.models import Brand, CarModel, Engine, Generation, Variant
from core.provenance import FieldProvenance, Source

T = TypeVar("T")
ATTR = "Data from openvehicle-data (https://github.com/mirkobechini/openvehicle-data), CC BY 4.0. See NOTICE for upstream sources."


class Page(BaseModel, Generic[T]):
    total: int
    limit: int
    offset: int
    items: list[T]


class VariantDetail(Variant):
    engine: Engine
    provenance: list[FieldProvenance]


class Found(BaseModel):
    brands: list[Brand]
    models: list[CarModel]


class Meta(BaseModel):
    version: str
    license: str
    attribution: str
    counts: dict[str, int]
    sources: list[Source]


def page(st, cls, lo, q=None, **w):
    return {
        "total": st.count(cls, q=q, **w),
        "limit": lo[0],
        "offset": lo[1],
        "items": st.find(cls, q=q, limit=lo[0], offset=lo[1], **w),
    }


def one(st, cls, i):
    o = st.get(cls, i)
    if o is None:
        raise LookupError(f"{cls.__name__} {i} not found")
    return o


def _ix(cur, ids):
    ids = set(ids)
    return ids if cur is None else cur & ids


def variants_page(st, lo, q=None, model_id=None, generation_id=None, engine_id=None, fuel=None):
    w, g, e = {}, None, None
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
    return page(st, Variant, lo, q, **w)


def variant_detail(st, i):
    v = one(st, Variant, i)
    e = st.get(Engine, v.engine_id)
    return VariantDetail(**v.model_dump(), engine=e, provenance=[*st.prov(v.id), *st.prov(e.id)])


def search(st, q):
    return Found(brands=st.find(Brand, q=q, limit=10), models=st.find(CarModel, q=q, limit=10))


def meta(st, version):
    cs = {c.__name__: st.count(c) for c in (Brand, CarModel, Generation, Engine, Variant, Source)}
    return Meta(version=version, license="CC-BY-4.0", attribution=ATTR, counts=cs, sources=st.find(Source))
