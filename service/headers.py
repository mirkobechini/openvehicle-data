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
