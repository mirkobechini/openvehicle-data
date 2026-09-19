import os
from contextlib import asynccontextmanager, contextmanager
from importlib.metadata import version
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from mcp.server.transport_security import TransportSecuritySettings
from starlette.routing import Route

from core.enums import Fuel
from core.models import Brand, CarModel, Engine, Generation, Variant
from core.provenance import Source
from core.storage import Store
from service import queries as qs
from service.mcp_server import build_mcp
from service.queries import ATTR, Found, Meta, Page, VariantDetail

Q = Annotated[str | None, Query(min_length=1, description="Case-insensitive search in name and aliases")]


def _pg(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    return limit, offset


Pg = Annotated[tuple[int, int], Depends(_pg)]


def _get(fn, *a):
    try:
        return fn(*a)
    except LookupError as e:
        raise HTTPException(404, str(e)) from None


def create_app(db=None):
    p = Path(db or os.environ.get("OVD_DB", "openvehicle-data.db"))
    if not p.is_file():
        raise FileNotFoundError(p)
    mcp = build_mcp(p)
    mcp_app = mcp.streamable_http_app(
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )

    @asynccontextmanager
    async def life(_):
        async with mcp.session_manager.run():
            yield

    app = FastAPI(
        title="openvehicle-data",
        version=version("openvehicle-data"),
        description="Open, verified vehicle brand/model/spec data. Read-only. " + ATTR,
        lifespan=life,
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
            return qs.meta(st, app.version)

    @app.get("/api/v1/brands", response_model=Page[Brand])
    def brands(pg: Pg, q: Q = None):
        with rd() as st:
            return qs.page(st, Brand, pg, q)

    @app.get("/api/v1/brands/{i}", response_model=Brand)
    def brand(i: str):
        with rd() as st:
            return _get(qs.one, st, Brand, i)

    @app.get("/api/v1/models", response_model=Page[CarModel])
    def models(pg: Pg, q: Q = None, brand_id: str | None = None):
        with rd() as st:
            return qs.page(st, CarModel, pg, q, **({"brand_id": brand_id} if brand_id else {}))

    @app.get("/api/v1/models/{i}", response_model=CarModel)
    def model(i: str):
        with rd() as st:
            return _get(qs.one, st, CarModel, i)

    @app.get("/api/v1/generations", response_model=Page[Generation])
    def generations(pg: Pg, model_id: str | None = None):
        with rd() as st:
            return qs.page(st, Generation, pg, **({"model_id": model_id} if model_id else {}))

    @app.get("/api/v1/engines", response_model=Page[Engine])
    def engines(pg: Pg, fuel: Fuel | None = None):
        with rd() as st:
            return qs.page(st, Engine, pg, **({"fuel": fuel} if fuel else {}))

    @app.get("/api/v1/engines/{i}", response_model=Engine)
    def engine(i: str):
        with rd() as st:
            return _get(qs.one, st, Engine, i)

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
            return qs.variants_page(st, pg, q, model_id, generation_id, engine_id, fuel)

    @app.get("/api/v1/variants/{i}", response_model=VariantDetail)
    def variant(i: str):
        with rd() as st:
            return _get(qs.variant_detail, st, i)

    @app.get("/api/v1/sources", response_model=list[Source])
    def sources():
        with rd() as st:
            return st.find(Source)

    @app.get("/api/v1/search", response_model=Found)
    def search(q: Annotated[str, Query(min_length=1)]):
        with rd() as st:
            return qs.search(st, q)

    app.router.routes.append(Route("/mcp", endpoint=mcp_app))
    return app
