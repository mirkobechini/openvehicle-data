from enum import StrEnum

from core.enums import Fuel
from core.ids import slug
from core.models import Base, Brand, CarModel, Engine, Family, Generation, Variant
from core.provenance import Source, Status

RANGES = [
    (Variant, "mass_kg", 400, 5000),
    (Variant, "wheelbase_mm", 1500, 4500),
    (Engine, "power_kw", None, 1000),
]
SPEC = {
    Brand: ("wikidata_id",),
    Engine: ("displacement_cc", "power_kw"),
    Variant: ("mass_kg", "wheelbase_mm", "track_width_mm", "co2_wltp_g_km", "type_approval"),
}
COMB = {Fuel.PETROL, Fuel.DIESEL, Fuel.LPG, Fuel.CNG}


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


class Violation(Base):
    rule: str
    severity: Severity
    entity_id: str
    message: str


class BuildError(Exception):
    def __init__(self, vs):
        super().__init__(report(vs))
        self.violations = vs


def _e(rule, eid, msg):
    return Violation(rule=rule, severity=Severity.ERROR, entity_id=eid, message=msg)


def _w(rule, eid, msg):
    return Violation(rule=rule, severity=Severity.WARNING, entity_id=eid, message=msg)


def _ns(o):
    return {slug(o.name), *map(slug, o.aliases)} - {""}


def _ranges(st):
    for cls, f, lo, hi in RANGES:
        for o in st.find(cls):
            x = getattr(o, f)
            if x is not None and ((lo is not None and x < lo) or (hi is not None and x > hi)):
                yield _w("implausible_value", o.id, f"{f}={x} outside plausible range {lo}..{hi}")


def _units(st):
    for e in st.find(Engine):
        if e.fuel in COMB and e.displacement_cc is not None and e.displacement_cc < 100:
            yield _w("unit", e.id, f"displacement_cc={e.displacement_cc} looks like litres")


def _clash(rule, rows):
    seen = {}
    for i, g, ns in rows:
        for n in ns:
            seen.setdefault((g, n), set()).add(i)
    out = {}
    for (_, n), ids in seen.items():
        if len(ids) > 1:
            for i in ids:
                out.setdefault(i, []).append(n)
    for i, ns in out.items():
        yield _e(rule, i, f"name clash: {', '.join(sorted(ns))}")


def _dups(st):
    yield from _clash("brand_duplicate", [(b.id, None, _ns(b)) for b in st.find(Brand)])
    yield from _clash("model_duplicate", [(m.id, m.brand_id, _ns(m)) for m in st.find(CarModel)])
    yield from _clash(
        "variant_duplicate",
        [(v.id, (v.generation_id, v.engine_id), _ns(v)) for v in st.find(Variant)],
    )


def _years(st):
    gs = {g.id: g for g in st.find(Generation)}
    for v in st.find(Variant):
        g = gs[v.generation_id]
        if v.year_from < g.year_from or (g.year_to is not None and (v.year_to is None or v.year_to > g.year_to)):
            yield _w("variant_years", v.id, f"{v.year_from}-{v.year_to} outside generation {g.year_from}-{g.year_to}")


def _prov(st):
    ss = {s.id: s for s in st.find(Source)}
    for cls, fs in SPEC.items():
        for o in st.find(cls):
            ps = {p.field: p for p in st.prov(o.id)}
            for f in fs:
                x = getattr(o, f)
                p = ps.get(f)
                if x is None:
                    continue
                if p is None:
                    yield _e("missing_provenance", o.id, f"{f} has no source")
                    continue
                for ev in p.evidence:
                    s = ss.get(ev.source_id)
                    if s is None:
                        yield _e("unknown_source", o.id, f"{f}: source {ev.source_id} not registered")
                    elif not s.usable:
                        yield _e("unlicensed_source", o.id, f"{f}: license of {ev.source_id} not verified")
                if x not in {ev.value for ev in p.evidence}:
                    yield _e("value_unsupported", o.id, f"{f}={x} not supported by any evidence")
                if p.status is Status.CONFLICT:
                    yield _w("source_conflict", o.id, f"{f}: sources disagree")


def _families(st):
    fs = {f.id: f for f in st.find(Family)}
    tot = {}
    for m in st.find(CarModel):
        if m.family_id is None:
            yield _w("family_missing", m.id, "model has no family")
            continue
        f = fs[m.family_id]
        if f.brand_id != m.brand_id:
            yield _e("family_brand", m.id, f"family {f.id} belongs to {f.brand_id}, not {m.brand_id}")
        n, r = tot.get(f.id, (0, 0))
        tot[f.id] = (n + 1, r + (m.registrations or 0))
    for i, f in fs.items():
        n, r = tot.get(i, (0, 0))
        if f.model_count != n or (f.registrations or 0) != r:
            yield _e("family_totals", i, f"model_count={f.model_count}, registrations={f.registrations} do not match its {n} models ({r})")


def validate(st):
    vs = [*_ranges(st), *_units(st), *_dups(st), *_years(st), *_prov(st), *_families(st)]
    return sorted(vs, key=lambda v: (v.severity != Severity.ERROR, v.rule, v.entity_id))


def report(vs):
    if not vs:
        return "no violations"
    n = sum(v.severity is Severity.ERROR for v in vs)
    ls = [f"{v.severity.upper()} {v.rule} {v.entity_id}: {v.message}" for v in vs]
    return "\n".join([*ls, f"{n} errors, {len(vs) - n} warnings"])


def ensure(st):
    vs = validate(st)
    if any(v.severity is Severity.ERROR for v in vs):
        raise BuildError(vs)
    return vs
