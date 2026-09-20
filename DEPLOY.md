# Deployment guide

One Render web service runs the REST API and the MCP server from a Docker image.
The image contains the dataset (`openvehicle-data.db`), downloaded at build time
from a GitHub Release and checked against a SHA-256.

```
GitHub Release (data)  -->  Dockerfile (ADD --checksum)  -->  Render service
                                                              /api/v1/...  REST
                                                              /mcp         MCP
Optional: your own domain (Cloudflare DNS) --> the same service
```

## 1. Publish the first data release

```bash
python -m pipeline.build --years 2019-2025 --version 0.1.0 --out dist
gh release create data-v0.1.0 dist/* --title "Data 0.1.0" --notes-file dist/CHANGELOG.md
```

Then point the Dockerfile at it: set the defaults of `DATA_URL`
(`https://github.com/<owner>/openvehicle-data/releases/download/data-v0.1.0/openvehicle-data.db`)
and `DATA_SHA256` (the `openvehicle-data.db` entry in `dist/manifest.json`), and
merge that change to `dev`.

The releases up to `data-v0.6.0` are already published and the Dockerfile points
at the latest one, so this step is only needed for a new data version.

## 2. Release to `main`

Render deploys from `main` (see `render.yaml`). Follow the release flow in
`AGENT_FLOW.md`: a PR from `dev` to `main`, merged by the maintainer.

## 3. Create the service on Render

1. Sign in to Render and connect your GitHub account.
2. New > Blueprint, pick this repository, and apply `render.yaml`.
3. Wait for the first build. The service is healthy when
   `https://<service>.onrender.com/api/v1/health` returns `{"status":"ok"}`.

The Blueprint declares no custom domain: the service is reachable at its own
address, `https://<service>.onrender.com`, for both the REST API and the MCP server.

## 4. Check that everything works

Replace `<service>` with the name in the service address shown by Render.

```bash
curl https://<service>.onrender.com/api/v1/meta
curl -X POST https://<service>.onrender.com/mcp   -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream'   -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

Connect an MCP client, for example Claude Code:

```bash
claude mcp add --transport http openvehicle https://<service>.onrender.com/mcp
```

## 5. Optional: your own domain on Cloudflare

Render's free workspaces allow 2 custom domains; a third needs a payment method
on the account (or removing one you no longer use). Once a slot is free:

1. Add `domains: [openvehicle.<domain>]` to the service in `render.yaml`, or add
   the domain in the Render dashboard (Settings > Custom Domains).
2. Cloudflare, SSL/TLS > Overview: set the encryption mode to **Full**.
3. DNS: add one CNAME record, `openvehicle`, pointing to `<service>.onrender.com`,
   with proxy status **DNS only**.
4. In Render wait until the domain is verified and its certificate issued.
5. Optionally switch the record to **Proxied**. Then add a rate-limiting rule
   (Security > WAF > Rate limiting rules), for example 60 requests per minute per
   IP on the hostname, since the API has no authentication.

## Updating the data

Build the new version against the previous export so the changelog is generated,
publish a new release, update `DATA_URL` and `DATA_SHA256` in the Dockerfile and
merge. The `checksPass` deploy trigger redeploys once CI is green.

```bash
python -m pipeline.build --years 2019-2025 --version 0.2.0 --prev dist --out dist2
gh release create data-v0.2.0 dist2/* --title "Data 0.2.0" --notes-file dist2/CHANGELOG.md
```

## Things to know

- **No rate limiting on the plain address:** without your own domain behind
  Cloudflare, nothing limits requests to the API. Fine for an early release; add
  the domain and the rule from step 5 before promoting it.
- **Free plan:** the service sleeps after 15 minutes without requests and takes
  about a minute to wake up. Clients that time out earlier will fail on the first
  call, and MCP clients use POST, which is the case most likely to hit this. For
  real use, switch the plan to `starter` in `render.yaml`.
- **Build fails with `digest mismatch`:** `DATA_SHA256` does not match the file at
  `DATA_URL`. Take the value from the release's `manifest.json`.
- **Domain does not verify:** the record is still Proxied. Set it to DNS only until
  Render reports the certificate as issued.
- **Rollback:** redeploy an earlier commit from the Render dashboard, or revert the
  Dockerfile change that bumped the data version.
