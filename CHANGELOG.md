# Changelog

All notable changes to the **software** (API, MCP server, pipeline). The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

Two version numbers exist and are independent:

- **Software**: the number in `pyproject.toml`, reported by `/api/v1/meta` as `software_version`.
  Released: `0.1.0` and `0.1.1` (both 2026-10-19).
- **Dataset**: tags `data-vX.Y.Z`, reported as `version`. Each data release carries its own
  `CHANGELOG.md` listing ids added, removed and changed.

The dataset schema has its own number, `schema_version` (now 2). The service refuses to start
with a dataset of another schema, so this software needs a dataset built with it.

## [Unreleased]

## [0.1.1] - 2026-10-19

### Added
- The monthly refresh publishes the data release and opens a pull request that moves the Docker pin; it needs one merge to go live (#168).
- CI builds and runs the Docker image; `pipeline.refresh` has `guard` and `pin` commands (#168).

### Changed
- The changelog ignores case-only differences in aliases (#168).

## [0.1.0] - 2026-10-19

### Added
- Type-approval number read from the EEA data (`TAN`): nearly every variant has one (99.98%,
  was 47%); the RDW now cross-checks it (#125).
- `type_code`, `variant_code`, `version_code` on variants (field D.2 of the registration
  document) and the matching filters on `GET /variants` and MCP `list_variants` (#127, #131).
- `seats`, `max_mass_kg` (field F.2) and `environmental_class` (`Euro 0`-`Euro 6`) from the
  RDW (#147).
- `years` on variants: the years with registrations (#137).
- `GET /api/v1/coverage` and `meta.coverage`: how many variants have each field, overall and
  per brand, also weighted by registrations; the build prints the overall coverage (#135).
- `Cache-Control` and `ETag` on `GET /api/v1/*`, with `304` on `If-None-Match` (#133).
- Rate limit: 120 requests per minute per client (`OVD_RATE_LIMIT`), `429` with `Retry-After`
  (#143).
- `Content-Security-Policy`, `Permissions-Policy` and HSTS with `includeSubDomains` (#143).
- Search by several words, ignoring accents; a word may match the brand of a model (#151).
- `schema_version` in the dataset and `/meta`, checked at startup (#153).
- Indexes for the type-approval, code, engine, registrations and fuel queries (#129).
- Landing page at `/` with a name search and a registration-document lookup, mobile-first and accessible (#159).
- Hashed lock files (`requirements.lock`, `requirements-dev.lock`), version bounds in `pyproject.toml`,
  base image pinned by digest, and a workflow to refresh the locks (#157).
- Importer stage registry and a shared CLI helper for new data sources (#149).

### Changed
- The `year` filter now matches the years a variant was actually registered, not the range
  between its first and last year (#137).
- The RDW cross-check matches variants by their codes instead of by splitting the name; 23,270 variants match on the real data (variants
  with an empty part used to be skipped) (#127).
- When the same measurement was split across spellings of a model, the importer now adds the
  registrations up before choosing the value; 10 variants changed CO2 by 1 g/km (#125).
- `uvicorn` no longer trusts forwarded headers from any address; the client address for the
  rate limit is the last `X-Forwarded-For` entry (#143).
- `PRIVACY.md` and `ADR.md` no longer say that Cloudflare sits in front of the service (#145).
- `eea._load` split into steps; variant filters grouped in `VariantQuery` (#139, #141).

### Notes for upgrading
- Needs dataset 0.10.0 or later (schema 2); the `Dockerfile` pins `data-v0.10.0`.
  A dataset of another schema makes the service refuse to start.

## Before this changelog

Releases 0.1.0 to 0.9.0 of the dataset (Wikidata brand ids, RDW cross-check, families,
type-approval filter, year filter) are described in `ADR.md` and in the GitHub releases.
