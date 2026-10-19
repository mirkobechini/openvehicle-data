import os
from contextlib import asynccontextmanager, contextmanager
from importlib.metadata import version
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from mcp.server.transport_security import TransportSecuritySettings
from starlette.routing import Route

from core.coverage import Coverage
from core.enums import Fuel
from core.models import Brand, CarModel, Engine, Family, Generation, Variant
from core.provenance import Source
from core.storage import Store
from service import queries as qs
from service.headers import Cache, Headers, RateLimit
from service.mcp_server import build_mcp
from service.queries import ATTR, Found, Meta, Page, VariantDetail

Q = Annotated[str | None, Query(min_length=1, max_length=100, description="Case-insensitive search in name and aliases")]
Sort = Annotated[Literal["id", "registrations"], Query(description="'registrations' lists the most registered first")]
Yr = Annotated[int | None, Query(ge=1900, le=2100, description="Only variants registered in this year")]
Ta = Annotated[str | None, Query(pattern=r"^\s*[eE]\d{1,3}\*[^*\s]+\*[^*\s]+(\*[^*\s]+)?\s*$", description="EU type-approval number as on the registration document, e.g. e3*2007/46*0064*05 or without the last part")]
MinReg = Annotated[int | None, Query(ge=0, description="Only entries with at least this many registrations")]


def _pg(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    return limit, offset


Pg = Annotated[tuple[int, int], Depends(_pg)]


def _get(fn, *a):
    try:
        return fn(*a)
    except LookupError as e:
        raise HTTPException(404, str(e)) from None


def create_app(db=None, rate=None):
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

    @app.get("/api/v1/coverage", response_model=Coverage)
    def cover(brand_id: str | None = None):
        with rd() as st:
            return _get(qs.coverage_of, st, brand_id)

    @app.get("/api/v1/brands", response_model=Page[Brand])
    def brands(pg: Pg, q: Q = None):
        with rd() as st:
            return qs.page(st, Brand, pg, q)

    @app.get("/api/v1/brands/{i}", response_model=Brand)
    def brand(i: str):
        with rd() as st:
            return _get(qs.one, st, Brand, i)

    @app.get("/api/v1/families", response_model=Page[Family])
    def families(pg: Pg, q: Q = None, brand_id: str | None = None, sort: Sort = "id", min_registrations: MinReg = None):
        with rd() as st:
            return _get(qs.families_page, st, pg, q, brand_id, sort, min_registrations)

    @app.get("/api/v1/families/{i}", response_model=Family)
    def family(i: str):
        with rd() as st:
            return _get(qs.one, st, Family, i)

    @app.get("/api/v1/models", response_model=Page[CarModel])
    def models(pg: Pg, q: Q = None, brand_id: str | None = None, family_id: str | None = None, sort: Sort = "id", min_registrations: MinReg = None):
        with rd() as st:
            return _get(qs.models_page, st, pg, q, brand_id, sort, min_registrations, family_id)

    @app.get("/api/v1/models/{i}", response_model=CarModel)
    def model(i: str):
        with rd() as st:
            return _get(qs.one, st, CarModel, i)

    @app.get("/api/v1/generations", response_model=Page[Generation])
    def generations(pg: Pg, model_id: str | None = None):
        with rd() as st:
            return _get(qs.generations_page, st, pg, model_id)

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
        brand_id: str | None = None,
        family_id: str | None = None,
        model_id: str | None = None,
        generation_id: str | None = None,
        engine_id: str | None = None,
        fuel: Fuel | None = None,
        sort: Sort = "id",
        min_registrations: MinReg = None,
        year: Yr = None,
        type_approval: Ta = None,
        type_code: Annotated[str | None, Query(min_length=1, max_length=40, description="Vehicle type, first part of field D.2 of the registration document, e.g. 312")] = None,
        variant_code: Annotated[str | None, Query(min_length=1, max_length=40, description="Variant, second part of D.2, e.g. PYD1B")] = None,
        version_code: Annotated[str | None, Query(min_length=1, max_length=40, description="Version, third part of D.2, e.g. AA4")] = None,
    ):
        with rd() as st:
            f = qs.VariantQuery(q=q, brand_id=brand_id, family_id=family_id, model_id=model_id, generation_id=generation_id, engine_id=engine_id, fuel=fuel, sort=sort, min_registrations=min_registrations, year=year, type_approval=type_approval, type_code=type_code, variant_code=variant_code, version_code=version_code)
            return _get(qs.variants_page, st, pg, f)

    @app.get("/api/v1/variants/{i}", response_model=VariantDetail)
    def variant(i: str):
        with rd() as st:
            return _get(qs.variant_detail, st, i)

    @app.get("/api/v1/sources", response_model=list[Source])
    def sources():
        with rd() as st:
            return st.find(Source)

    @app.get("/api/v1/search", response_model=Found)
    def search(q: Annotated[str, Query(min_length=1, max_length=100)]):
        with rd() as st:
            return qs.search(st, q)

    app.router.routes.append(Route("/mcp", endpoint=mcp_app))
    with rd() as st:
        tag = f"{st.get_meta('version')}|{st.get_meta('generated')}|{app.version}"
    app.add_middleware(Cache, tag=tag)
    app.add_middleware(RateLimit, limit=int(os.environ.get("OVD_RATE_LIMIT", 120)) if rate is None else rate)
    app.add_middleware(Headers)
    return app
