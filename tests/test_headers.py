import asyncio

from service.headers import H, Cache, Headers
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


def test_api_answers_are_cacheable_with_an_etag(cl):
    r = cl.get(f"{B}/brands", params={"q": "fiat"})
    assert r.headers["cache-control"] == "public, max-age=3600" and r.headers["etag"].startswith('"')
    assert has(r)


def test_etag_depends_on_the_url(cl):
    a, b = cl.get(f"{B}/brands").headers["etag"], cl.get(f"{B}/brands", params={"q": "fiat"}).headers["etag"]
    assert a != b and a == cl.get(f"{B}/brands").headers["etag"]


def test_matching_if_none_match_gets_a_304_without_a_body(cl):
    r = cl.get(f"{B}/models")
    r2 = cl.get(f"{B}/models", headers={"If-None-Match": r.headers["etag"]})
    assert r2.status_code == 304 and r2.content == b"" and r2.headers["etag"] == r.headers["etag"]
    assert r2.headers["cache-control"] == "public, max-age=3600" and has(r2)


def test_if_none_match_accepts_weak_and_lists(cl):
    e = cl.get(f"{B}/models").headers["etag"]
    assert cl.get(f"{B}/models", headers={"If-None-Match": f'"x", W/{e}'}).status_code == 304


def test_a_stale_etag_gets_the_full_answer(cl):
    r = cl.get(f"{B}/models", headers={"If-None-Match": '"old"'})
    assert r.status_code == 200 and r.json()["items"]


def test_an_etag_for_one_url_does_not_match_another(cl):
    e = cl.get(f"{B}/models").headers["etag"]
    assert cl.get(f"{B}/brands", headers={"If-None-Match": e}).status_code == 200


def test_health_errors_docs_and_writes_are_not_cached(cl):
    for r in (cl.get(f"{B}/health"), cl.get(f"{B}/variants/nope"), cl.get("/docs"), cl.post(f"{B}/brands")):
        assert "etag" not in r.headers and "cache-control" not in r.headers
    assert cl.get(f"{B}/health", headers={"If-None-Match": "*"}).status_code == 200


def test_the_tag_changes_with_the_dataset_version(db, tmp_path):
    import shutil

    from fastapi.testclient import TestClient

    from core.storage import Store
    from service.app import create_app

    p = tmp_path / "v.db"
    shutil.copy(db, p)
    a = TestClient(create_app(p)).get(f"{B}/brands").headers["etag"]
    with Store(p) as s:
        s.set_meta("version", "9.9.9")
    assert TestClient(create_app(p)).get(f"{B}/brands").headers["etag"] != a


def test_only_api_gets_pass_through_the_cache():
    sent = []

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})

    async def snd(m):
        sent.append(m)

    for sc in ({"type": "http", "method": "POST", "path": "/mcp", "headers": [], "query_string": b""}, {"type": "http", "method": "POST", "path": "/api/v1/brands", "headers": [], "query_string": b""}, {"type": "lifespan", "method": "GET", "path": "/api/v1/brands", "headers": [], "query_string": b""}):
        asyncio.run(Cache(app, "t")(sc, None, snd))
    assert all(m["headers"] == [] for m in sent) and len(sent) == 3
