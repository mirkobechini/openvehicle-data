# Deployment guide

One Render web service runs the REST API and the MCP server from a Docker image.
The image contains the dataset (`openvehicle-data.db`), downloaded at build time
from a GitHub Release and checked against a SHA-256.

```
GitHub Release (data)  -->  Dockerfile (ADD --checksum)  -->  Render service
                                                              /api/v1/...  REST
                                                              /mcp         MCP
Cloudflare DNS: openvehicle-api.<domain>, openvehicle-mcp.<domain> --> the same service
```

## 1. Publish the first data release

```bash
python -m pipeline.build --table co2cars_2025Pv31 --year 2025 --version 0.1.0 --out dist
gh release create data-v0.1.0 dist/* --title "Data 0.1.0" --notes-file dist/CHANGELOG.md
```

Then point the Dockerfile at it: set the defaults of `DATA_URL`
(`https://github.com/<owner>/openvehicle-data/releases/download/data-v0.1.0/openvehicle-data.db`)
and `DATA_SHA256` (the `openvehicle-data.db` entry in `dist/manifest.json`), and
merge that change to `dev`.

## 2. Release to `main`

Render deploys from `main` (see `render.yaml`). Follow the release flow in
`AGENT_FLOW.md`: a PR from `dev` to `main`, merged by the maintainer.

## 3. Create the service on Render

1. Sign in to Render and connect your GitHub account.
2. New > Blueprint, pick this repository, and apply `render.yaml`.
3. Wait for the first build. The service is healthy when
   `https://<service>.onrender.com/api/v1/health` returns `{"status":"ok"}`.

The Blueprint also declares the two custom domains. Change them in
`render.yaml` if you use other names.

## 4. DNS on Cloudflare

1. SSL/TLS > Overview: set the encryption mode to **Full**.
2. DNS: add two CNAME records, `openvehicle-api` and `openvehicle-mcp`, both
   pointing to `<service>.onrender.com`, with proxy status **DNS only**.
3. In Render (Settings > Custom Domains) wait until both domains are verified and
   their certificates issued.
4. Optionally switch both records to **Proxied**. Then add a rate-limiting rule
   (Security > WAF > Rate limiting rules), for example 60 requests per minute per
   IP on the hostnames, since the API has no authentication.

## 5. Check that everything works

```bash
curl https://openvehicle-api.<domain>/api/v1/meta
curl -X POST https://openvehicle-mcp.<domain>/mcp \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

Connect an MCP client, for example Claude Code:

```bash
claude mcp add --transport http openvehicle https://openvehicle-mcp.<domain>/mcp
```

## Updating the data

Build the new version against the previous export so the changelog is generated,
publish a new release, update `DATA_URL` and `DATA_SHA256` in the Dockerfile and
merge. The `checksPass` deploy trigger redeploys once CI is green.

```bash
python -m pipeline.build --table <table> --year <year> --version 0.2.0 --prev dist --out dist2
gh release create data-v0.2.0 dist2/* --title "Data 0.2.0" --notes-file dist2/CHANGELOG.md
```

## Things to know

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
