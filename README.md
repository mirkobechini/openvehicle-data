# openvehicle-data

Open, verified data on vehicle brands, models and technical specifications.
Distributed as a versioned dataset, a read-only REST API and an MCP server, so
apps, AI agents and fleet-management tools can use it. Italy first, then EU and
beyond.

## Status

Early development. Pre-release datasets are published on the Releases page
(`data-v*` tags). The data targets passenger cars (EU category M1) registered in
Italy from 2019 to 2025, built only from sources with clear open licenses.
Implemented so far: the EEA CO2 monitoring data importer (about 49,000 variants
for Italy, 2019-2024 final and 2025 provisional). The build cross-checks mass,
engine size, wheelbase and engine power with the Dutch RDW open data (about half of the variants
are found there and get `confirmed` or `conflict`); Variants found there also carry the EU
type-approval number (`type_approval`, filterable), as on the registration
document. Wikidata enrichment is planned.

Known limits: no trims or equipment; wheelbase and track width only for vehicles
registered in 2019-2022 (the EEA stopped reporting them from 2023); names as
reported by the EEA (upper case; spellings that differ only by spaces or hyphens are
merged, a few near-duplicates with reordered words remain, and models can still be
split by trim or engine for brands without family rules); the years of
a variant are the registration years seen in the data (2019-2025), not production
years.

## Quick start

```bash
python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"   # Linux/macOS: .venv/bin/pip

# build the dataset (downloads 2019-2025 from the EEA and the RDW, validates, exports
# to ./dist; add --skip-rdw to skip the RDW cross-check)
python -m pipeline.build --years 2019-2025 --version 0.1.0 --out dist

# serve the REST API (docs at /docs) and the MCP server (at /mcp)
OVD_DB=dist/openvehicle-data.db uvicorn --factory service.app:create_app

# tests, with the required 100% coverage
coverage run -m pytest tests/ -q && coverage report
```

The export folder holds a SQLite copy, one CSV per table, `dataset.json`,
`manifest.json` (with SHA-256 of every file) and a changelog against the
previous release (`--prev <folder>`).

## Principles

- Every technical specification field (mass, CO2, engine size and power, wheelbase,
  track width) records its source, license, `last_verified` date and verification
  status (single source, confirmed when two sources agree, or conflict; the sources EEA and RDW both derive from the manufacturer's type-approval data, so agreement rules out transcription errors but is not a second measurement). Fuel, years,
  names and registration counts come from the same EEA data but carry no source
  record of their own.
- Cars only in v0.1 (category M1). Vans, trucks and motorcycles are out of scope for now.
- No personal data, no plate or VIN lookups, no prices.
- Known mistakes in the source data (a wrong make, brand spelled several ways) are
  fixed through a small reviewed file, `pipeline/importers/corrections.json`, where
  every entry has a written reason. Proposals are welcome as pull requests.
- Models are grouped into families (Mercedes `GLC`, BMW `X1`, Volkswagen `ID.4`) by
  reviewed rules per brand, `pipeline/importers/families.json`; a brand without rules
  keeps one family per model.
- Models and variants carry `registrations` (cars registered in the source data), so
  clients can sort by popularity and skip one-off or mistyped entries.

## Layout

- `core/`: shared models and storage
- `pipeline/`: batch import, validation, verification and export
- `service/`: read-only API and MCP server

## Licenses

- Code: Apache-2.0 (`LICENSE`)
- Data: CC BY 4.0 (`LICENSE-DATA`); sources and attributions in `NOTICE`

## Privacy

The public API and MCP server use no accounts, cookies or analytics. See
[PRIVACY.md](PRIVACY.md).

## Disclaimer

The data is provided "as is", without warranty of any kind. Verify it before any
safety-critical use. This project is not affiliated with any vehicle
manufacturer; brand and model names are trademarks of their respective owners.
