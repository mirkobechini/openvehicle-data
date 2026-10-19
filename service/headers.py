import hashlib

C = [(b"cache-control", b"public, max-age=3600")]
H = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"strict-transport-security", b"max-age=31536000"),
]


class Headers:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        async def snd(m):
            if m["type"] == "http.response.start":
                m["headers"] = [*m.get("headers", []), *H]
            await send(m)

        await self.app(scope, receive, snd)


class Cache:
    def __init__(self, app, tag):
        self.app = app
        self.tag = tag

    def ok(self, scope):
        p = scope["path"]
        return scope["type"] == "http" and scope["method"] in ("GET", "HEAD") and p.startswith("/api/v1/") and p != "/api/v1/health"

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
