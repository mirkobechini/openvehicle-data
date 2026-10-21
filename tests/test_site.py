import re
import tomllib
from html.parser import HTMLParser
from pathlib import Path

from fastapi.testclient import TestClient

from service.app import SITE
from service.headers import CSP, SITE as SITE_CSP, csp
from tests.test_api import B, cl, db  # noqa: F401


def test_home_serves_the_page_with_its_own_csp_and_a_cache(cl):
    r = cl.get("/")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert r.headers["cache-control"] == "public, max-age=3600"
    assert r.headers["content-security-policy"] == SITE_CSP[1].decode()
    assert "script-src 'self'" in r.headers["content-security-policy"] and "unsafe-inline" not in r.headers["content-security-policy"]
    assert 'name="viewport"' in r.text and '<html lang="en">' in r.text


def test_browse_serves_the_page_with_its_own_csp_and_a_cache(cl):
    r = cl.get("/browse")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert r.headers["cache-control"] == "public, max-age=3600"
    assert r.headers["content-security-policy"] == SITE_CSP[1].decode()
    assert 'name="viewport"' in r.text and '<html lang="en">' in r.text
    j = cl.get("/static/browse.js")
    assert j.headers["content-type"].startswith("text/javascript") and j.headers["content-security-policy"] == SITE_CSP[1].decode()


def test_coverage_serves_the_page_with_its_own_csp_and_a_cache(cl):
    r = cl.get("/coverage")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert r.headers["cache-control"] == "public, max-age=3600"
    assert r.headers["content-security-policy"] == SITE_CSP[1].decode()
    assert 'name="viewport"' in r.text and '<html lang="en">' in r.text
    j = cl.get("/static/coverage.js")
    assert j.headers["content-type"].startswith("text/javascript") and j.headers["content-security-policy"] == SITE_CSP[1].decode()


def test_assets_are_served_with_the_right_types(cl):
    c = cl.get("/static/site.css")
    j = cl.get("/static/site.js")
    k = cl.get("/static/common.js")
    assert c.headers["content-type"].startswith("text/css") and "prefers-color-scheme" in c.text
    assert j.headers["content-type"].startswith("text/javascript") and "addEventListener" in j.text
    assert k.headers["content-type"].startswith("text/javascript") and "textContent" in k.text
    assert j.headers["content-security-policy"] == k.headers["content-security-policy"] == SITE_CSP[1].decode()


def test_unknown_static_paths_and_the_api_keep_the_strict_policy(cl):
    assert cl.get("/static/other.js").status_code == 404
    assert cl.get(f"{B}/brands").headers["content-security-policy"] == CSP[1].decode()
    assert csp("/docs") == () and csp("/redoc") == () and csp("/") == (SITE_CSP,) and csp("/static/x") == (SITE_CSP,) and csp("/mcp") == (CSP,)
    assert csp("/browse") == (SITE_CSP,) and csp("/coverage") == (SITE_CSP,)


def test_the_page_is_not_in_the_openapi(cl):
    paths = cl.get("/openapi.json").json()["paths"]
    assert not {"/", "/browse", "/coverage", "/static/site.js", "/static/browse.js", "/static/coverage.js"} & set(paths)


class Scan(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids, self.fors, self.inputs, self.external, self.inline = set(), set(), [], [], 0

    def handle_starttag(self, tag, a):
        a = dict(a)
        if "id" in a:
            self.ids.add(a["id"])
        if tag == "label":
            self.fors.add(a.get("for"))
        if tag == "input":
            self.inputs.append(a)
        for k in ("src", "href"):
            if a.get(k, "").startswith(("http://", "https://")) and tag in ("script", "link", "img"):
                self.external.append(a[k])
        if tag == "script" and "src" not in a:
            self.inline += 1


def test_page_markup_is_accessible_and_self_contained():
    s = Scan()
    s.feed((SITE / "index.html").read_text(encoding="utf-8"))
    assert all(i["id"] in s.fors for i in s.inputs), "every input needs a label"
    assert {"main", "q", "ta", "tc", "vc", "nc", "r-search", "r-doc", "meta"} <= s.ids
    assert s.external == [] and s.inline == 0
    html = (SITE / "index.html").read_text(encoding="utf-8")
    assert 'href="#main"' in html and html.count("aria-live=\"polite\"") == 2 and "<h1>" in html


def test_every_page_links_the_same_three_sections():
    for name in ("index.html", "browse.html", "coverage.html"):
        html = (SITE / name).read_text(encoding="utf-8")
        assert 'href="/"' in html and 'href="/browse"' in html and 'href="/coverage"' in html
        assert html.count('aria-current="page"') == 1


def test_browse_page_markup_is_accessible_and_self_contained():
    s = Scan()
    s.feed((SITE / "browse.html").read_text(encoding="utf-8"))
    assert {"main", "rail", "r-models", "meta"} <= s.ids
    assert s.external == [] and s.inline == 0
    html = (SITE / "browse.html").read_text(encoding="utf-8")
    assert 'href="#main"' in html and 'aria-live="polite"' in html and "<h1>" in html


def test_coverage_page_markup_is_accessible_and_self_contained():
    s = Scan()
    s.feed((SITE / "coverage.html").read_text(encoding="utf-8"))
    assert {"main", "r-overall", "sorters", "r-table", "meta"} <= s.ids
    assert s.external == [] and s.inline == 0
    html = (SITE / "coverage.html").read_text(encoding="utf-8")
    assert 'href="#main"' in html and html.count('aria-live="polite"') == 2 and "<h1>" in html


def test_script_never_writes_html_and_uses_relative_urls():
    for name in ("common.js", "site.js", "browse.js", "coverage.js"):
        js = (SITE / name).read_text(encoding="utf-8")
        assert not re.search(r"innerHTML|outerHTML|insertAdjacentHTML|document\.write|eval\(", js)
        assert "https://" not in js
    assert 'const API = "/api/v1"' in (SITE / "common.js").read_text(encoding="utf-8")


def test_display_names_are_a_reviewed_exception_table_used_everywhere():
    common = (SITE / "common.js").read_text(encoding="utf-8")
    assert '"KA+": "Ka+"' in common and "KA: \"Ka\"" in common
    for name in ("site.js", "browse.js", "coverage.js"):
        js = (SITE / name).read_text(encoding="utf-8")
        assert "disp(" in js and "disp } = window.OVD" in js


def test_css_has_the_accessibility_basics():
    css = (SITE / "site.css").read_text(encoding="utf-8")
    assert "prefers-color-scheme: dark" in css and ":focus-visible" in css and "min-height: 2.75rem" in css


def test_robots_txt_allows_everything_and_points_to_the_sitemap(cl):
    r = cl.get("/robots.txt")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain")
    assert "Allow: /" in r.text and "Sitemap: https://openvehicle-data.onrender.com/sitemap.xml" in r.text


def test_sitemap_lists_the_three_pages(cl):
    r = cl.get("/sitemap.xml")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/xml")
    for path in ("/", "/browse", "/coverage"):
        assert f"<loc>https://openvehicle-data.onrender.com{path}</loc>" in r.text


def test_dataset_jsonld_is_valid_and_linked_from_the_home_page(cl):
    import json

    r = cl.get("/static/dataset.jsonld")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/ld+json")
    data = json.loads(r.text)
    assert data["@type"] == "Dataset" and data["license"] == "https://creativecommons.org/licenses/by/4.0/"
    assert '<script type="application/ld+json" src="/static/dataset.jsonld"></script>' in (SITE / "index.html").read_text(encoding="utf-8")


def test_site_files_are_packaged():
    p = tomllib.loads((Path(__file__).parent.parent / "pyproject.toml").read_text(encoding="utf-8"))
    assert "site/*" in p["tool"]["setuptools"]["package-data"]["service"]
    assert {f.name for f in SITE.iterdir()} == {"index.html", "browse.html", "coverage.html", "site.css", "site.js", "common.js", "browse.js", "coverage.js", "favicon.svg", "favicon-32.png", "apple-touch-icon.png", "robots.txt", "sitemap.xml", "dataset.jsonld"}


def test_the_rate_limit_applies_to_the_page_too(db):
    from service.app import create_app

    c = TestClient(create_app(db, rate=2))
    assert [c.get("/").status_code for _ in range(3)] == [200, 200, 429]


def test_card_formats_numbers_the_italian_way_and_reads_the_new_fields():
    js = (SITE / "common.js").read_text(encoding="utf-8")
    assert 'new Intl.NumberFormat("it-IT", { useGrouping: "always" })' in js
    assert "1.35962" in js and "v.brand.name" in js and "v.model.registrations" in js
    for tag in ("P.1", "P.2", "P.3", "S.1", "F.2", "V.7", "V.9", "K"):
        assert f'"{tag}"' in js
    assert "navigator.clipboard" in js and 'role", "status"' in js


def test_hidden_elements_stay_hidden_and_the_filter_has_a_label():
    css = (SITE / "site.css").read_text(encoding="utf-8")
    assert "[hidden] { display: none !important; }" in css
    js = (SITE / "common.js").read_text(encoding="utf-8")
    assert "lab.htmlFor = sel.id" in js


def test_the_icons_are_served_with_the_right_types(cl):
    for path, kind in (("/static/favicon.svg", "image/svg+xml"), ("/static/favicon-32.png", "image/png"), ("/static/apple-touch-icon.png", "image/png"), ("/favicon.ico", "image/png")):
        r = cl.get(path)
        assert r.status_code == 200 and r.headers["content-type"] == kind and r.headers["cache-control"] == "public, max-age=3600"
    assert cl.get("/static/favicon-32.png").content[:8] == b"\x89PNG\r\n\x1a\n" == cl.get("/favicon.ico").content[:8]
    assert cl.get("/static/favicon.svg").text.lstrip().startswith(("<?xml", "<svg"))


def test_the_page_links_the_icons_and_the_svg_is_inert():
    html = (SITE / "index.html").read_text(encoding="utf-8")
    for h in ("/static/favicon.svg", "/static/favicon-32.png", "/static/apple-touch-icon.png"):
        assert f'href="{h}"' in html
    svg = (SITE / "favicon.svg").read_text(encoding="utf-8").lower()
    assert not re.search(r"<script|onload|onclick|<foreignobject|<image|href=\"http", svg)
