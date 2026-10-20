# Security policy

## Supported versions

Only the latest release of the software (`main` branch, the version in
`pyproject.toml`) is supported. Older releases do not receive security fixes.

## Reporting a vulnerability

Please **do not** open a public issue for a security vulnerability.

Instead, use GitHub's private vulnerability reporting for this repository:
[github.com/mirkobechini/openvehicle-data/security/advisories/new](https://github.com/mirkobechini/openvehicle-data/security/advisories/new).
If that is not available to you, open an issue asking for a private channel,
without any detail about the vulnerability itself, and we will follow up.

Please include:

- what you found and where (a URL, endpoint or file)
- steps to reproduce it
- what you think the impact is

We will acknowledge a report within a few days and aim to fix a confirmed
vulnerability before disclosing it publicly. There is no bug bounty: this is a
small open source project maintained outside working hours.

## Scope

- The REST API and MCP server (`service/`)
- The data pipeline (`pipeline/`), including the importers and their external
  requests
- The Docker image and the GitHub Actions workflows

## Out of scope

- The data itself (accuracy issues in the vehicle catalogue are not security
  vulnerabilities; open a regular issue instead, following
  [Contributing](README.md#contributing))
- Third-party services the project depends on (Render, GitHub, the upstream
  data sources): report those to their own maintainers
- Denial of service through sheer request volume against the public instance,
  which Render and the application's own rate limit are meant to absorb; a way
  to *bypass* that rate limit is in scope

## Notes for reporters

- No authentication exists on the public API or MCP server: there are no
  credentials to steal, and the dataset has no personal data by design (see
  [PRIVACY.md](PRIVACY.md)).
- The database is read-only in the running service; `core.storage.Store` opens
  it with SQLite's `mode=ro`.
- Dependencies are pinned with hashes (`requirements.lock`) and audited weekly
  by `pip-audit` (`.github/workflows/audit.yml`); the Docker base image is
  pinned by digest.
