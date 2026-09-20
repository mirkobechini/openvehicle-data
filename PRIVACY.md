# Privacy notice

Last updated: 2026-09-20

This notice covers the public services of the openvehicle-data project: the REST
API and the MCP server.

## The short version

The services do not ask who you are. There are no accounts, no cookies and no
analytics. Like any web server, they see your IP address and what you request.

## What we process

When you call the API or the MCP server, the request reaches our servers with:

- your IP address
- the address you requested, including search terms in the query string
- the time of the request and your client's user agent

The dataset itself contains no personal data: it describes vehicle models, not
owners, plates or people. While building the dataset, one licence plate per vehicle
version is read from the Dutch RDW open data and held in memory only, to look up
that version's engine power; plates are never stored, published or logged.

## Who processes it and why

The requests pass through:

- **Cloudflare**, which the hosting network uses in front of the services to filter
  abuse (see the [Cloudflare privacy policy](https://www.cloudflare.com/privacypolicy/)).
  The project does not limit request rates yet.
- **Render**, which hosts the services and keeps their logs
  (see the [Render privacy policy](https://render.com/privacy)).

We use this only to run and protect the service: to find errors and to stop
abuse. We do not sell it, share it for advertising or build profiles from it.
The application itself writes its log to the hosting platform and stores nothing
else about visitors. How long the providers keep their logs is set by them.

Downloading the dataset from GitHub is covered by the
[GitHub privacy statement](https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement).

## Contributors

If you contribute to the repository, your name and email address appear in the
public git history. They cannot be removed from it later without rewriting history.

## Your rights and contact

If you are in the EU you can ask what we hold about you, or ask us to delete it,
to the extent that we hold anything beyond what the providers above keep on their
side. Use the [issues page](https://github.com/mirkobechini/openvehicle-data/issues)
and do not post personal data in a public issue: ask for a private channel instead.

The person responsible for the project is Mirko Bechini.
