import hashlib
import json
import time
from collections import deque

C = [(b"cache-control", b"public, max-age=3600")]
H = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"strict-transport-security", b"max-age=31536000; includeSubDomains"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=(), payment=()"),
]
CSP = (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'")
DOCS = ("/docs", "/redoc")
SITE = (b"content-security-policy", b"default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")


def csp(path):
    if path.startswith(DOCS):
        return ()
    return (SITE,) if path == "/" or path.startswith("/static/") else (CSP,)


class Headers:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        async def snd(m):
            if m["type"] == "http.response.start":
                m["headers"] = [*m.get("headers", []), *H, *csp(scope.get("path", ""))]
            await send(m)

        await self.app(scope, receive, snd)


def client_ip(scope):
    xf = next((v.decode("latin-1") for k, v in scope["headers"] if k == b"x-forwarded-for"), "")
    last = xf.rsplit(",", 1)[-1].strip()
    return last or (scope.get("client") or ("?",))[0]


class RateLimit:
    def __init__(self, app, limit, window=60):
        self.app = app
        self.limit = limit
        self.window = window
        self.hits = {}

    async def __call__(self, scope, receive, send):
        if not self.limit or scope["type"] != "http" or scope["path"] == "/api/v1/health":
            return await self.app(scope, receive, send)
        now = time.monotonic()
        q = self.hits.setdefault(client_ip(scope), deque())
        while q and now - q[0] >= self.window:
            q.popleft()
        if len(q) >= self.limit:
            body = json.dumps({"detail": "Too many requests"}).encode()
            h = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()), (b"retry-after", str(int(self.window - (now - q[0])) + 1).encode())]
            await send({"type": "http.response.start", "status": 429, "headers": h})
            return await send({"type": "http.response.body", "body": body})
        q.append(now)
        if len(self.hits) > 10000:
            self.hits = {k: v for k, v in self.hits.items() if v and now - v[-1] < self.window}
        await self.app(scope, receive, send)


class Cache:
    def __init__(self, app, tag):
        self.app = app
        self.tag = tag

    def ok(self, scope):
        return scope["type"] == "http" and scope["method"] == "GET" and scope["path"].startswith("/api/v1/") and scope["path"] != "/api/v1/health"

    async def __call__(self, scope, receive, send):
        if not self.ok(scope):
            return await self.app(scope, receive, send)
        et = '"' + hashlib.sha256(f"{self.tag}|{scope['path']}|{scope['query_string'].decode('latin-1')}".encode()).hexdigest()[:20] + '"'
        if et in [x.strip().removeprefix("W/") for k, v in scope["headers"] if k == b"if-none-match" for x in v.decode("latin-1").split(",")]:
            await send({"type": "http.response.start", "status": 304, "headers": [(b"etag", et.encode()), *C]})
            return await send({"type": "http.response.body", "body": b""})

        async def snd(m):
            if m["type"] == "http.response.start" and m["status"] == 200:
                m["headers"] = [*m.get("headers", []), (b"etag", et.encode()), *C]
            await send(m)

        await self.app(scope, receive, snd)
