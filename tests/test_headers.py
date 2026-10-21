import asyncio

from service.headers import CSP, DOCS, H, Cache, Headers, RateLimit, client_ip
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
    assert sent[0]["headers"] == [(b"x-a", b"1"), *H, CSP] and sent[1] == {"type": "http.response.body", "body": b"ok"}
    assert sent[2]["headers"] == [*H, CSP]


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


def test_csp_and_permissions_policy_on_api_but_not_on_docs(cl):
    r = cl.get(f"{B}/brands")
    assert r.headers["content-security-policy"] == "default-src 'none'; frame-ancestors 'none'"
    assert "geolocation=()" in r.headers["permissions-policy"] and r.headers["strict-transport-security"].endswith("includeSubDomains")
    assert "content-security-policy" not in cl.get("/docs").headers and "content-security-policy" not in cl.get("/redoc").headers
    assert "content-security-policy" in cl.get("/openapi.json").headers
    assert DOCS == ("/docs", "/redoc")


def scope(xf=None, client=("1.2.3.4", 1), path="/api/v1/brands"):
    return {"type": "http", "path": path, "method": "GET", "headers": [(b"x-forwarded-for", xf.encode())] if xf is not None else [], "query_string": b"", "client": client}


def test_client_ip_is_the_last_forwarded_entry_then_the_socket():
    assert client_ip(scope("9.9.9.9, 5.6.7.8")) == "5.6.7.8"
    assert client_ip(scope(" 5.6.7.8 ")) == "5.6.7.8"
    assert client_ip(scope("")) == "1.2.3.4" and client_ip(scope()) == "1.2.3.4"
    assert client_ip(scope(client=None)) == "?"


def run(app, sc):
    out = []

    async def snd(m):
        out.append(m)

    asyncio.run(app(sc, None, snd))
    return out


async def ok(scope, receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


def test_rate_limit_blocks_after_the_limit_with_retry_after():
    app = RateLimit(ok, 2)
    assert [run(app, scope())[0]["status"] for _ in range(2)] == [200, 200]
    r = run(app, scope())
    assert r[0]["status"] == 429 and b'"Too many requests"' in r[1]["body"]
    h = dict(r[0]["headers"])
    assert 1 <= int(h[b"retry-after"]) <= 61 and h[b"content-type"] == b"application/json"


def test_rate_limit_is_per_client_and_follows_the_forwarded_address():
    app = RateLimit(ok, 1)
    assert run(app, scope("1.1.1.1"))[0]["status"] == 200
    assert run(app, scope("2.2.2.2"))[0]["status"] == 200
    assert run(app, scope("1.1.1.1"))[0]["status"] == 429
    assert run(app, scope("9.9.9.9, 2.2.2.2"))[0]["status"] == 429


def test_rate_limit_window_expires(monkeypatch):
    t = [0.0]
    monkeypatch.setattr("service.headers.time.monotonic", lambda: t[0])
    app = RateLimit(ok, 1, window=10)
    assert run(app, scope())[0]["status"] == 200 and run(app, scope())[0]["status"] == 429
    t[0] = 10.0
    assert run(app, scope())[0]["status"] == 200


def test_rate_limit_skips_health_other_scopes_and_zero():
    app = RateLimit(ok, 1)
    assert all(run(app, scope(path="/api/v1/health"))[0]["status"] == 200 for _ in range(3))
    assert run(app, {**scope(), "type": "lifespan"})[0]["status"] == 200
    off = RateLimit(ok, 0)
    assert all(run(off, scope())[0]["status"] == 200 for _ in range(5))


def test_rate_limit_forgets_idle_clients(monkeypatch):
    t = [0.0]
    monkeypatch.setattr("service.headers.time.monotonic", lambda: t[0])
    app = RateLimit(ok, 5, window=10)
    for i in range(10001):
        run(app, scope(f"10.0.{i // 250}.{i % 250}"))
    assert len(app.hits) == 10001
    t[0] = 20.0
    run(app, scope("7.7.7.7"))
    assert list(app.hits) == ["7.7.7.7"]


def test_the_app_limits_requests_through_create_app(db):
    from fastapi.testclient import TestClient

    from service.app import create_app

    c = TestClient(create_app(db, rate=3))
    assert [c.get(f"{B}/brands").status_code for _ in range(4)] == [200, 200, 200, 429]
    r = c.get(f"{B}/brands")
    assert r.headers["retry-after"] and "content-security-policy" in r.headers
    assert c.get(f"{B}/health").status_code == 200


def test_the_default_limit_comes_from_the_environment(db, monkeypatch):
    from fastapi.testclient import TestClient

    from service.app import create_app

    monkeypatch.setenv("OVD_RATE_LIMIT", "1")
    c = TestClient(create_app(db))
    assert [c.get(f"{B}/brands").status_code for _ in range(2)] == [200, 429]


def test_large_responses_are_gzip_compressed(cl):
    r = cl.get(f"{B}/variants")
    assert r.headers["content-encoding"] == "gzip" and r.json()["items"]


def test_tiny_responses_are_not_compressed(cl):
    assert "content-encoding" not in cl.get(f"{B}/health").headers
