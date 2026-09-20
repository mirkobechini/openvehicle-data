import asyncio

from service.headers import H, Headers
from tests.test_api import B, cl, db  # noqa: F401

EXPECTED = {k.decode(): v.decode() for k, v in H}


def has(r):
    return all(r.headers.get(k) == v for k, v in EXPECTED.items())


def test_rest_responses_carry_the_headers(cl):
    assert has(cl.get(f"{B}/health"))
    assert has(cl.get(f"{B}/brands"))


def test_errors_and_other_paths_carry_the_headers(cl):
    assert has(cl.get(f"{B}/variants/nope"))
    assert has(cl.get(f"{B}/variants", params={"limit": 0}))
    assert has(cl.get("/docs"))
    assert has(cl.post(f"{B}/brands"))


def test_existing_headers_are_kept_and_other_messages_pass_through():
    sent = []

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": [(b"x-a", b"1")]})
        await send({"type": "http.response.body", "body": b"ok"})
        await send({"type": "http.response.start", "status": 200})

    async def snd(m):
        sent.append(m)

    asyncio.run(Headers(app)({"type": "http"}, None, snd))
    assert sent[0]["headers"] == [(b"x-a", b"1"), *H] and sent[1] == {"type": "http.response.body", "body": b"ok"}
    assert sent[2]["headers"] == H
