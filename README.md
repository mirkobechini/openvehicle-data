# openvehicle-data

[![CI](https://github.com/mirkobechini/openvehicle-data/actions/workflows/ci.yml/badge.svg)](https://github.com/mirkobechini/openvehicle-data/actions/workflows/ci.yml)
![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)
![Code: Apache-2.0](https://img.shields.io/badge/code-Apache--2.0-green)
![Data: CC BY 4.0](https://img.shields.io/badge/data-CC%20BY%204.0-green)

Open, verified data on passenger cars: brands, models, versions and technical
specifications, for the cars registered in **Italy from 2019 to 2025** (EU category
M1), with Europe and the world to follow.

It is published three ways, all read-only and free:

- a **dataset** (SQLite, CSV and JSON) on the [Releases](https://github.com/mirkobechini/openvehicle-data/releases) page;
- a **REST API** with interactive documentation;
- an **MCP server**, so AI agents can look vehicles up themselves.

Every technical value says where it comes from, and where two sources agree it says
so. There is no personal data: no owners, no plates, no VIN lookups.

> **Status: early development.** Datasets are pre-releases (`data-v*` tags) and the
> schema can still change. See [Limits](#limits) before relying on it.

## Contents

[Try it](#try-it) · [The data](#the-data) · [REST API](#rest-api) · [MCP server](#mcp-server) ·
[Run it yourself](#run-it-yourself) · [Limits](#limits) · [Contributing](#contributing) ·
[Documentation](#documentation) · [Licenses](#licenses-and-attribution)

## Try it

With a server running (see [Run it yourself](#run-it-yourself)), on its default local
address:

```bash
U=http://localhost:8000/api/v1

# find a model by name (typos get a "did_you_mean")
curl "$U/search?q=panda"

# the most registered Toyota variants seen in 2023
curl "$U/variants?brand_id=brand_toyota&year=2023&sort=registrations&limit=5"

# one variant, with its engine and the source of every field
curl "$U/variants/var_fiat-panda-312-pyd1b-s5g"

# match the number on an Italian registration document (carta di circolazione)
curl "$U/variants?type_approval=e3*2007/46*0064*05"
```

Interactive documentation is at `/docs` on the same host.

## The data

### Structure

```
Brand ─ Family ─ Model ─ Generation ─ Variant ─ Engine
FIAT    PANDA    PANDA    observed    312 PYD1B S5G   hybrid 999 cc 52 kW
```

| Level | What it is | Example id |
| --- | --- | --- |
| Brand | the make | `brand_fiat` |
| Family | models that differ only by engine, drive or trim (Mercedes `GLC`, BMW `X1`, VW `ID.4`) | `family_fiat-panda` |
| Model | the commercial name as reported by the source | `model_fiat-panda` |
| Generation | `observed`: the years the model was seen in the data | `gen_fiat-panda-observed` |
| Variant | a type-approval version (type, variant and version codes) | `var_fiat-panda-312-pyd1b-s5g` |
| Engine | fuel, displacement and power | `eng_hybrid-999-52` |

Ids are stable and readable. Lists are sorted by id in the REST API and by
registrations in the MCP server, and both accept `min_registrations` to skip rare or
mistyped entries.

### What a variant holds

| Field | Meaning |
| --- | --- |
| `name`, `aliases` | the type/variant/version codes, as reported |
| `year_from`, `year_to` | first and last registration year seen (2019-2025), not production years |
| `mass_kg` | mass in running order |
| `wheelbase_mm`, `track_width_mm` | only for vehicles registered in 2019-2022 |
| `co2_wltp_g_km` | WLTP combined CO2 |
| `registrations` | cars registered in Italy in the source data, summed over the years |
| `type_approval` | EU type-approval base number, e.g. `e3*2007/46*0064` (about half of the variants) |
| `engine` | fuel, `displacement_cc`, `power_kw` |

Brands also carry a `wikidata_id` where a reliable match was reviewed.

### Where each value comes from

Every technical field (mass, CO2, wheelbase, track width, engine size and power, type
approval, Wikidata id) has its own record: source, licence, evidence link,
`last_verified` date and a status. `get_variant` and `GET /variants/{id}` return them.

| Status | Meaning |
| --- | --- |
| `single_source` | one source only |
| `confirmed` | two sources agree, within a tolerance (mass 1 kg, wheelbase 10 mm, power 1 kW, displacement exact) |
| `conflict` | two sources disagree; the value shown is the EEA one and the difference stays visible |

`confirmed` is a check against transcription and aggregation errors, not a second
measurement: both sources derive from the manufacturer's type-approval data.

| Source | Provides | Licence |
| --- | --- | --- |
| [EEA](https://www.eea.europa.eu/data-and-maps/data/co2-cars-emission-22) CO2 monitoring, Regulation (EU) 2019/631 | the catalogue itself: makes, models, versions, engines, mass, CO2, registrations (2019-2024 final, 2025 provisional) | CC BY 4.0 |
| [RDW](https://opendata.rdw.nl) open data (Netherlands) | second source for mass, wheelbase, engine size and power; the type-approval number | Public Domain |
| [Wikidata](https://www.wikidata.org) | brand identifiers, from a reviewed list | CC0 |

RDW rows are one per licence plate, so they are grouped on the RDW server: no plate
is stored, published or logged.

### Downloads

Each release has `openvehicle-data.db` (SQLite), one CSV per table (`brands`,
`families`, `models`, `generations`, `engines`, `variants`, `provenance`, `sources`),
`dataset.json`, `manifest.json` (SHA-256 of every file) and a changelog against the
previous release.

## REST API

Base path `/api/v1`. Everything is `GET`.

| Path | Filters |
| --- | --- |
| `/brands`, `/brands/{id}` | `q` |
| `/families`, `/families/{id}` | `q`, `brand_id`, `sort`, `min_registrations` |
| `/models`, `/models/{id}` | `q`, `brand_id`, `family_id`, `sort`, `min_registrations` |
| `/generations` | `model_id` |
| `/engines`, `/engines/{id}` | `fuel` |
| `/variants` | `q`, `brand_id`, `family_id`, `model_id`, `generation_id`, `engine_id`, `fuel`, `year`, `type_approval`, `sort`, `min_registrations` |
| `/variants/{id}` | the variant, its engine and the provenance of every field |
| `/search?q=` | brands, families and models by name or alias |
| `/sources`, `/meta`, `/health` | sources and licences; version, counts and attribution; liveness |

Lists take `limit` (default 50, at most 200) and `offset`, and answer with `total`,
`count`, `has_more` and `next_offset`. `sort` is `id` or `registrations`.
`type_approval` accepts the full number as printed on the registration document or
only its base. An unknown id gives a 404 with a "Did you mean" suggestion; a
malformed value gives a 422.

## MCP server

Endpoint `/mcp` (Streamable HTTP, stateless, no authentication). Add your server to
an MCP client, for example Claude Code:

```bash
claude mcp add --transport http openvehicle http://localhost:8000/mcp
```

| Tool | Use it to |
| --- | --- |
| `search_catalog` | find brands, families and models by name or alias |
| `list_brands`, `list_families`, `list_models` | browse, most registered first |
| `list_variants` | filter by brand, family, model, engine, fuel, year or type-approval number |
| `get_variant` | one variant with the source, licence and status of every field |
| `dataset_info` | counts, sources, version and the attribution text to cite |

Names and codes come from public datasets, so the server tells clients to treat them
as data, never as instructions, and it replaces oversized or non-printable strings.
Ask an agent, for instance: *"Which diesel Peugeot 3008 variants were registered in
2022, and what is the source of their CO2 value?"*

## Run it yourself

Python 3.12 or newer.

```bash
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"      # Linux/macOS: .venv/bin/pip

# build the dataset: downloads 2019-2025 from the EEA and the RDW (about 4 minutes),
# validates, and exports to ./dist  (--skip-rdw skips the RDW cross-check)
python -m pipeline.build --years 2019-2025 --version 0.1.0 --out dist

# serve the REST API (docs at /docs) and the MCP server (at /mcp)
OVD_DB=dist/openvehicle-data.db uvicorn --factory service.app:create_app
```

`--years` also takes one year (`2025`) or a list (`2021,2023`); `--prev <folder>`
compares with a previous export and writes the changelog. The build stops without
writing anything if validation finds an error.

Docker: the image downloads a pinned data release and checks its SHA-256.

```bash
docker build -t openvehicle-data . && docker run -p 10000:10000 openvehicle-data
```

Tests, with the required 100% coverage:

```bash
coverage run -m pytest tests/ -q && coverage report
```

A monthly GitHub Actions job rebuilds the data and opens an issue if anything
changed; it never publishes by itself. Deployment (Render, data releases, a custom
domain) is described in [DEPLOY.md](DEPLOY.md).

## Limits

- Cars only (category M1). No vans, trucks or motorcycles, no trims or equipment, no prices.
- Only vehicles registered in Italy, 2019-2025. Years are registration years.
- Names are as the EEA reports them, in upper case. Spellings that differ only by
  spaces, hyphens or case are merged; a few near-duplicates remain.
- Family rules cover 50 brands; the other brands keep one family per model.
- Wheelbase and track width exist only for 2019-2022 (the EEA stopped reporting them).
- RDW covers about half of the variants (cars sold in the Netherlands), so the rest
  stay `single_source`. CO2 is single-source everywhere: RDW's per-plate values vary
  too much between cars of one variant to serve as a check.
- Wikidata ids exist for 70 of 90 brands; models are not linked (Wikidata has
  duplicate and mixed items for them).
- The API has no authentication and no rate limiting of its own: put it behind a
  proxy that limits requests if you expose it publicly (see [DEPLOY.md](DEPLOY.md)).

## Contributing

Known mistakes in the sources are fixed through small reviewed files, each entry with
a written reason, so a proposal is a pull request that edits one of them:

| File | Fixes |
| --- | --- |
| `pipeline/importers/corrections.json` | brands spelled several ways, wrong makes, models to merge |
| `pipeline/importers/families.json` | which models form a family, per brand |
| `pipeline/importers/wikidata.json` | the Wikidata id of a brand |

Work goes through issues and pull requests to `dev`; `main` only receives reviewed
releases. Keep the 100% test coverage. Please do not put personal data in issues.

## Documentation

- [ADR.md](ADR.md): architecture decisions and the measurements behind them (in Italian)
- [DEPLOY.md](DEPLOY.md): data releases, Render, domain and rate limiting
- [PRIVACY.md](PRIVACY.md): what the public service processes
- [NOTICE](NOTICE): sources and their licences
- Layout: `core/` models and storage · `pipeline/` import, validation and export · `service/` API and MCP server

## Licenses and attribution

- Code: Apache-2.0 ([LICENSE](LICENSE)).
- Data: CC BY 4.0 ([LICENSE-DATA](LICENSE-DATA)); sources and their licences in [NOTICE](NOTICE).

If you use the data, cite: *Data from openvehicle-data
(https://github.com/mirkobechini/openvehicle-data), CC BY 4.0. See NOTICE for upstream
sources.* The same text is returned by `dataset_info` and `/meta`.

## Disclaimer

The data is provided "as is", without warranty of any kind. Verify it before any
safety-critical use. This project is not affiliated with any vehicle manufacturer;
brand and model names are trademarks of their respective owners.
