import os
from contextlib import contextmanager
from importlib.metadata import version
from pathlib import Path
from typing import Annotated, Generic, TypeVar

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from core.enums import Fuel
from core.models import Brand, CarModel, Engine, Generation, Variant
from core.provenance import FieldProvenance, Source
from core.storage import Store

T = TypeVar("T")
Q = Annotated[str | None, Query(min_length=1, description="Case-insensitive search in name and aliases")]
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


def _pg(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    return limit, offset


Pg = Annotated[tuple[int, int], Depends(_pg)]


def _page(st, cls, pg, q=None, **w):
    return {
        "total": st.count(cls, q=q, **w),
        "limit": pg[0],
        "offset": pg[1],
        "items": st.find(cls, q=q, limit=pg[0], offset=pg[1], **w),
    }


def _one(st, cls, i):
    o = st.get(cls, i)
    if o is None:
        raise HTTPException(404, f"{cls.__name__} {i} not found")
    return o


def _ix(cur, ids):
    ids = set(ids)
    return ids if cur is None else cur & ids


def create_app(db=None):
    p = Path(db or os.environ.get("OVD_DB", "openvehicle-data.db"))
    if not p.is_file():
        raise FileNotFoundError(p)
    app = FastAPI(
        title="openvehicle-data",
        version=version("openvehicle-data"),
        description="Open, verified vehicle brand/model/spec data. Read-only. " + ATTR,
    )
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"])

    @contextmanager
    def rd():
        with Store(p, ro=True) as st:
            yield st

    @app.get("/api/v1/health")
    def health():
        with rd() as st:
            st.count(Brand)
        return {"status": "ok"}

    @app.get("/api/v1/meta", response_model=Meta)
    def meta():
        with rd() as st:
            cs = {c.__name__: st.count(c) for c in (Brand, CarModel, Generation, Engine, Variant, Source)}
            return Meta(version=app.version, license="CC-BY-4.0", attribution=ATTR, counts=cs, sources=st.find(Source))

    @app.get("/api/v1/brands", response_model=Page[Brand])
    def brands(pg: Pg, q: Q = None):
        with rd() as st:
            return _page(st, Brand, pg, q)

    @app.get("/api/v1/brands/{i}", response_model=Brand)
    def brand(i: str):
        with rd() as st:
            return _one(st, Brand, i)

    @app.get("/api/v1/models", response_model=Page[CarModel])
    def models(pg: Pg, q: Q = None, brand_id: str | None = None):
        with rd() as st:
            return _page(st, CarModel, pg, q, **({"brand_id": brand_id} if brand_id else {}))

    @app.get("/api/v1/models/{i}", response_model=CarModel)
    def model(i: str):
        with rd() as st:
            return _one(st, CarModel, i)

    @app.get("/api/v1/generations", response_model=Page[Generation])
    def generations(pg: Pg, model_id: str | None = None):
        with rd() as st:
            return _page(st, Generation, pg, **({"model_id": model_id} if model_id else {}))

    @app.get("/api/v1/engines", response_model=Page[Engine])
    def engines(pg: Pg, fuel: Fuel | None = None):
        with rd() as st:
            return _page(st, Engine, pg, **({"fuel": fuel} if fuel else {}))

    @app.get("/api/v1/engines/{i}", response_model=Engine)
    def engine(i: str):
        with rd() as st:
            return _one(st, Engine, i)

    @app.get("/api/v1/variants", response_model=Page[Variant])
    def variants(
        pg: Pg,
        q: Q = None,
        model_id: str | None = None,
        generation_id: str | None = None,
        engine_id: str | None = None,
        fuel: Fuel | None = None,
    ):
        with rd() as st:
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
            return _page(st, Variant, pg, q, **w)

    @app.get("/api/v1/variants/{i}", response_model=VariantDetail)
    def variant(i: str):
        with rd() as st:
            v = _one(st, Variant, i)
            e = st.get(Engine, v.engine_id)
            return VariantDetail(**v.model_dump(), engine=e, provenance=[*st.prov(v.id), *st.prov(e.id)])

    @app.get("/api/v1/sources", response_model=list[Source])
    def sources():
        with rd() as st:
            return st.find(Source)

    @app.get("/api/v1/search", response_model=Found)
    def search(q: Annotated[str, Query(min_length=1)]):
        with rd() as st:
            return Found(brands=st.find(Brand, q=q, limit=10), models=st.find(CarModel, q=q, limit=10))

    return app
