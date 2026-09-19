import json
import sqlite3
from pathlib import Path

from core.models import Brand, CarModel, Engine, Generation, Variant
from core.provenance import FieldProvenance, Source

TB = {
    Brand: "brands",
    CarModel: "models",
    Generation: "generations",
    Engine: "engines",
    Variant: "variants",
    Source: "sources",
}

DDL = """
CREATE TABLE IF NOT EXISTS brands (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, aliases TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS models (
    id TEXT PRIMARY KEY, brand_id TEXT NOT NULL REFERENCES brands(id),
    name TEXT NOT NULL, aliases TEXT NOT NULL, category TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS generations (
    id TEXT PRIMARY KEY, model_id TEXT NOT NULL REFERENCES models(id),
    name TEXT NOT NULL, aliases TEXT NOT NULL,
    year_from INTEGER NOT NULL, year_to INTEGER);
CREATE TABLE IF NOT EXISTS engines (
    id TEXT PRIMARY KEY, fuel TEXT NOT NULL,
    displacement_cc INTEGER, power_kw REAL);
CREATE TABLE IF NOT EXISTS variants (
    id TEXT PRIMARY KEY, generation_id TEXT NOT NULL REFERENCES generations(id),
    engine_id TEXT NOT NULL REFERENCES engines(id),
    name TEXT NOT NULL, aliases TEXT NOT NULL,
    year_from INTEGER NOT NULL, year_to INTEGER,
    mass_kg REAL, wheelbase_mm INTEGER, track_width_mm INTEGER,
    co2_wltp_g_km REAL);
CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, license TEXT NOT NULL,
    license_url TEXT NOT NULL, license_checked TEXT);
CREATE TABLE IF NOT EXISTS provenance (
    entity_id TEXT NOT NULL, field TEXT NOT NULL,
    last_verified TEXT NOT NULL, evidence TEXT NOT NULL,
    PRIMARY KEY (entity_id, field));
CREATE INDEX IF NOT EXISTS ix_models_brand ON models(brand_id);
CREATE INDEX IF NOT EXISTS ix_gens_model ON generations(model_id);
CREATE INDEX IF NOT EXISTS ix_vars_gen ON variants(generation_id);
"""


class Store:
    def __init__(self, path=":memory:", ro=False):
        if ro:
            self.c = sqlite3.connect(f"{Path(path).resolve().as_uri()}?mode=ro", uri=True)
        else:
            self.c = sqlite3.connect(path)
        self.c.row_factory = sqlite3.Row
        self.c.execute("PRAGMA foreign_keys=ON")
        if not ro:
            self.c.executescript(DDL)

    def close(self):
        self.c.close()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

    def _m(self, cls, r):
        d = dict(r)
        if "aliases" in d:
            d["aliases"] = json.loads(d["aliases"])
        return cls(**d)

    def put(self, *os):
        with self.c:
            for o in os:
                d = o.model_dump(mode="json")
                if "aliases" in d:
                    d["aliases"] = json.dumps(d["aliases"], ensure_ascii=False)
                cs = list(d)
                self.c.execute(
                    f"INSERT INTO {TB[type(o)]} ({','.join(cs)}) VALUES ({','.join('?' * len(cs))}) "
                    f"ON CONFLICT(id) DO UPDATE SET {','.join(f'{k}=excluded.{k}' for k in cs if k != 'id')}",
                    list(d.values()),
                )

    def get(self, cls, i):
        r = self.c.execute(f"SELECT * FROM {TB[cls]} WHERE id=?", (i,)).fetchone()
        return None if r is None else self._m(cls, r)

    def find(self, cls, **w):
        bad = set(w) - set(cls.model_fields)
        if bad:
            raise ValueError(f"unknown columns: {sorted(bad)}")
        q = f"SELECT * FROM {TB[cls]}"
        if w:
            q += " WHERE " + " AND ".join(f"{k}=?" for k in w)
        return [self._m(cls, r) for r in self.c.execute(f"{q} ORDER BY id", list(w.values()))]

    def put_prov(self, *ps):
        with self.c:
            for p in ps:
                d = p.model_dump(mode="json", exclude={"status"})
                self.c.execute(
                    "INSERT INTO provenance (entity_id, field, last_verified, evidence) VALUES (?,?,?,?) "
                    "ON CONFLICT(entity_id, field) DO UPDATE SET "
                    "last_verified=excluded.last_verified, evidence=excluded.evidence",
                    (d["entity_id"], d["field"], d["last_verified"], json.dumps(d["evidence"], ensure_ascii=False)),
                )

    def prov(self, eid):
        rs = self.c.execute("SELECT * FROM provenance WHERE entity_id=? ORDER BY field", (eid,))
        return [FieldProvenance(**{**dict(r), "evidence": json.loads(r["evidence"])}) for r in rs]
