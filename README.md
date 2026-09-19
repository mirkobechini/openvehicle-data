# openvehicle-data

Open, verified data on vehicle brands, models and technical specifications.
Distributed as a versioned dataset, a read-only REST API and an MCP server, so
apps, AI agents and fleet-management tools can use it. Italy first, then EU and
beyond.

## Status

Early development. No dataset release has been published yet. Version 0.1
targets passenger cars (EU category M1) sold in Italy, built only from sources
with clear open licenses. Implemented so far: the EEA CO2 monitoring data
importer (about 12,700 variants for Italy, 2025 provisional). Wikidata
enrichment and an RDW cross-check are planned.

Known limits of v0.1: no trims or equipment, no wheelbase or track width
(empty in the Italian EEA data), names as reported by the EEA (upper case, and a few
near-duplicates with reordered words such as `500 ABARTH` and `ABARTH 500`), and
only the years seen in the data (registration years, not production years).

## Quick start

```bash
python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"   # Linux/macOS: .venv/bin/pip

# build the dataset (downloads from the EEA, validates, exports to ./dist)
python -m pipeline.build --table co2cars_2025Pv31 --year 2025 --version 0.1.0 --out dist

# serve the REST API (docs at /docs) and the MCP server (at /mcp)
OVD_DB=dist/openvehicle-data.db uvicorn --factory service.app:create_app

# tests, with the required 100% coverage
coverage run -m pytest tests/ -q && coverage report
```

The export folder holds a SQLite copy, one CSV per table, `dataset.json`,
`manifest.json` (with SHA-256 of every file) and a changelog against the
previous release (`--prev <folder>`).

## Principles

- Every field records its source, license, `last_verified` date and
  verification status (single source vs. confirmed by two independent sources).
- Cars only in v0.1 (category M1). Vans, trucks and motorcycles are out of scope for now.
- No personal data, no plate or VIN lookups, no prices.
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
