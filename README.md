# openvehicle-data

Open, verified data on vehicle brands, models and technical specifications.
Distributed as a versioned dataset, a read-only REST API and an MCP server, so
apps, AI agents and fleet-management tools can use it. Italy first, then EU and
beyond.

## Status

Early development. No data has been published yet. Version 0.1 targets
passenger cars (EU category M1) sold in Italy, built only from sources with
clear open licenses: Wikidata, EEA CO2 monitoring data and RDW open data.

## Principles

- Every field records its source, license, `last_verified` date and
  verification status (single source vs. confirmed by two independent sources).
- Cars only in v0.1 (category M1). Vans, trucks and motorcycles are out of scope for now.
- No personal data, no plate or VIN lookups, no prices.

## Layout

- `core/`: shared models and storage
- `pipeline/`: batch import, validation, verification and export
- `service/`: read-only API and MCP server

## Licenses

- Code: Apache-2.0 (`LICENSE`)
- Data: CC BY 4.0 (`LICENSE-DATA`); sources and attributions in `NOTICE`

## Disclaimer

The data is provided "as is", without warranty of any kind. Verify it before any
safety-critical use. This project is not affiliated with any vehicle
manufacturer; brand and model names are trademarks of their respective owners.
