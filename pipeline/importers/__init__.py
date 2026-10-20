from dataclasses import dataclass
from datetime import date
from typing import Callable, Protocol


@dataclass
class Ctx:
    years: str
    ms: str = "IT"
    client: object = None
    today: date | None = None
    skip: frozenset = frozenset()


class Importer(Protocol):
    name: str

    def enabled(self, ctx: Ctx) -> bool: ...

    def run(self, db, ctx: Ctx) -> dict: ...


@dataclass
class Stage:
    name: str
    fn: Callable
    when: Callable = lambda ctx: True

    def enabled(self, ctx):
        return self.when(ctx)

    def run(self, db, ctx):
        return self.fn(db, ctx)


def stages():
    from pipeline.importers import eea, rdw, traficom, wikidata
    from pipeline.importers.eea_datasets import parse_years

    return [
        Stage("eea", lambda db, c: eea.run(db, c.years, c.ms, c.client, c.today)),
        Stage("rdw", lambda db, c: rdw.run(db, min(parse_years(c.years)), c.client, c.today), lambda c: "rdw" not in c.skip),
        Stage("traficom", lambda db, c: traficom.run(db, c.client, c.today), lambda c: "traficom" not in c.skip),
        Stage("wikidata", lambda db, c: wikidata.run(db, today=c.today)),
    ]
