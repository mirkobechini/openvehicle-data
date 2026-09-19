from datetime import date

from core.provenance import Source

EEA = Source(
    id="eea-co2",
    name="European Environment Agency - CO2 emissions from new passenger cars",
    license="CC-BY-4.0",
    license_url="https://creativecommons.org/licenses/by/4.0/",
    license_checked=date(2026, 9, 19),
)

SOURCES = {s.id: s for s in (EEA,)}
