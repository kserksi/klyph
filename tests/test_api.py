import base64
import hashlib
import json
import re
import struct
from xml.etree import ElementTree

import pytest
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request

from app.config import settings
from app.main import app, http_error_page, unhandled_error_page
from app.registry import FONTS


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def fonts_available() -> bool:
    return all(spec.path.is_file() for spec in FONTS.values())


def make_request(path: str, request_id: str = "error-request-1234") -> Request:
    request = Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": path,
            "raw_path": path.encode("ascii"),
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("localhost", 8000),
        }
    )
    request.state.request_id = request_id
    return request


def png_dimensions(content: bytes) -> tuple[int, int]:
    assert content[:8] == b"\x89PNG\r\n\x1a\n"
    assert content[12:16] == b"IHDR"
    return struct.unpack(">II", content[16:24])


def sha512_integrity(content: bytes) -> str:
    digest = base64.b64encode(hashlib.sha512(content).digest()).decode("ascii")
    return f"sha512-{digest}"


def test_only_required_fonts_are_registered():
    assert set(FONTS) == {"zen-kaku-regular", "zen-maru-regular", "zen-maru-bold"}


def test_health(client):
    assert client.get("/healthz").json() == {"status": "ok"}
    readiness = client.get("/readyz")
    assert readiness.status_code == 200
    assert readiness.json() == {"status": "ready", "detail": "ready"}


def test_request_id_and_security_headers(client):
    response = client.get("/healthz", headers={"X-Request-ID": "request-1234"})
    assert response.headers["x-request-id"] == "request-1234"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "same-origin"
    assert "default-src 'self'" in response.headers["content-security-policy"]


def test_rejects_oversized_body_without_relying_on_content_length(client):
    def chunks():
        yield b'{"font":"zen-kaku-regular","characters":"'
        yield b"x" * settings.max_request_bytes
        yield b'"}'

    response = client.post(
        "/v2/subsets",
        headers={
            "Content-Type": "application/json",
            "Transfer-Encoding": "chunked",
            "Origin": "http://localhost:8000",
        },
        content=chunks(),
    )
    assert response.status_code == 413
    assert response.headers["access-control-allow-origin"] == "http://localhost:8000"


def test_single_page_ui(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "必要な文字を、" in response.text
    assert "利用規約" in response.text
    assert "プライバシーポリシー" in response.text
    assert "textarea" not in response.text


def test_unknown_web_page_uses_branded_404(client):
    response = client.get(
        "/missing-page", headers={"X-Request-ID": "missing-request-1234"}
    )
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-robots-tag"] == "noindex, nofollow, noarchive"
    assert "ページが見つかりません" in response.text
    assert "missing-request-1234" in response.text
    assert "{{REQUEST_ID}}" not in response.text
    assert "{{TIMESTAMP}}" not in response.text


def test_unknown_machine_endpoint_keeps_json_error(client):
    response = client.get("/v2/missing")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"detail": "Not Found"}


@pytest.mark.asyncio
async def test_forbidden_web_request_uses_branded_403():
    response = await http_error_page(
        make_request("/private"),
        StarletteHTTPException(status_code=403, detail="private detail"),
    )
    assert response.status_code == 403
    assert response.media_type == "text/html"
    assert "このページには" in response.body.decode("utf-8")
    assert "private detail" not in response.body.decode("utf-8")


@pytest.mark.asyncio
async def test_unhandled_web_error_uses_safe_branded_500():
    response = await unhandled_error_page(
        make_request("/page"), RuntimeError("sensitive failure detail")
    )
    body = response.body.decode("utf-8")
    assert response.status_code == 500
    assert response.media_type == "text/html"
    assert response.headers["cache-control"] == "no-store"
    assert "処理を完了" in body
    assert "error-request-1234" in body
    assert "sensitive failure detail" not in body


@pytest.mark.asyncio
async def test_unhandled_machine_error_keeps_safe_json():
    response = await unhandled_error_page(
        make_request("/v2/subsets"), RuntimeError("sensitive failure detail")
    )
    assert response.status_code == 500
    assert response.media_type == "application/json"
    assert json.loads(response.body) == {"detail": "internal server error"}


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/terms", "利用規約"),
        ("/privacy", "プライバシーポリシー"),
        ("/licenses", "ライセンス・"),
        ("/components", "オープンソース・"),
    ],
)
def test_information_pages(client, path, expected):
    response = client.get(path)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert expected in response.text


@pytest.mark.parametrize(
    ("path", "canonical"),
    [
        ("/", f"{settings.public_base_url}/"),
        ("/terms", f"{settings.public_base_url}/terms"),
        ("/privacy", f"{settings.public_base_url}/privacy"),
        ("/licenses", f"{settings.public_base_url}/licenses"),
        ("/components", f"{settings.public_base_url}/components"),
    ],
)
def test_pages_have_complete_seo_metadata(client, path, canonical):
    response = client.get(path)
    html = response.text
    assert "{{PUBLIC_BASE_URL}}" not in html
    assert f'<link rel="canonical" href="{canonical}">' in html
    assert f'<meta property="og:url" content="{canonical}">' in html
    assert '<meta name="twitter:card" content="summary_large_image">' in html
    assert (
        f'<meta property="og:image" content="{settings.public_base_url}/og-image.png">'
        in html
    )
    assert '<meta property="og:image:width" content="1200">' in html
    assert '<meta property="og:image:height" content="630">' in html
    assert '<link rel="apple-touch-icon" href="/apple-touch-icon.png?v=20260714-2"' in html
    assert '<link rel="alternate" hreflang="ja"' in html
    assert '<link rel="alternate" hreflang="x-default"' in html
    assert '<link rel="manifest" href="/site.webmanifest">' in html

    match = re.search(
        r'<script type="application/ld\+json">([\s\S]*?)</script>', html
    )
    assert match is not None
    structured_data = json.loads(match.group(1))
    assert structured_data["@context"] == "https://schema.org"

    digest = base64.b64encode(
        hashlib.sha256(match.group(1).encode("utf-8")).digest()
    ).decode("ascii")
    assert f"'sha256-{digest}'" in response.headers["content-security-policy"]


def test_search_engine_discovery_files(client):
    robots = client.get("/robots.txt")
    assert robots.status_code == 200
    assert robots.headers["content-type"].startswith("text/plain")
    assert "Allow: /" in robots.text
    assert "Disallow:" not in robots.text
    assert f"Sitemap: {settings.public_base_url}/sitemap.xml" in robots.text

    sitemap = client.get("/sitemap.xml")
    assert sitemap.status_code == 200
    root = ElementTree.fromstring(sitemap.content)
    namespace = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    locations = {element.text for element in root.findall("s:url/s:loc", namespace)}
    assert locations == {
        f"{settings.public_base_url}/",
        f"{settings.public_base_url}/terms",
        f"{settings.public_base_url}/privacy",
        f"{settings.public_base_url}/licenses",
        f"{settings.public_base_url}/components",
    }


def test_components_page_tracks_production_lock(client):
    html = client.get("/components").text
    for component, version in {
        "FastAPI": "0.139.0",
        "Starlette": "1.3.1",
        "Uvicorn": "0.51.0",
        "Pydantic": "2.13.4",
        "FontTools": "4.63.0",
        "Brotli": "1.2.0",
        "Zopfli": "0.4.3",
    }.items():
        assert component in html
        assert version in html
    assert "requirements.lock" in html
    assert "開発・テスト専用ツールは含みません" in html


def test_licenses_page_credits_hero_artwork(client):
    html = client.get("/licenses").text
    assert '<section class="policy-section" id="artwork">' in html
    assert "Lilac" in html
    assert "https://www.pixiv.net/artworks/146748240" in html
    assert "Apache License 2.0 の対象外" in html


def test_manifest_and_favicon(client):
    manifest = client.get("/site.webmanifest")
    assert manifest.status_code == 200
    assert manifest.headers["content-type"].startswith("application/manifest+json")
    payload = manifest.json()
    assert payload["name"] == "Klyph"
    assert {(icon["src"], icon["sizes"]) for icon in payload["icons"]} >= {
        ("/icon-192.png?v=20260714-2", "192x192"),
        ("/icon-512.png?v=20260714-2", "512x512"),
    }

    favicon = client.get("/favicon.svg")
    assert favicon.status_code == 200
    assert favicon.headers["content-type"].startswith("image/svg+xml")
    assert "<svg" in favicon.text
    assert 'aria-label="Klyph"' in favicon.text
    assert "<text" not in favicon.text
    assert 'm20 36 8-12L45 7' in favicon.text


@pytest.mark.parametrize(
    ("path", "expected_dimensions"),
    [
        ("/og-image.png", (1200, 630)),
        ("/apple-touch-icon.png", (180, 180)),
        ("/icon-192.png", (192, 192)),
        ("/icon-512.png", (512, 512)),
    ],
)
def test_raster_brand_assets(client, path, expected_dimensions):
    response = client.get(path)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/png")
    assert png_dimensions(response.content) == expected_dimensions


@pytest.mark.parametrize("path", ["/healthz", "/readyz", "/sdk/v2.js"])
def test_machine_endpoints_are_not_indexable(client, path):
    assert client.get(path).headers["x-robots-tag"] == "noindex, nofollow"


def test_frontend_assets(client):
    stylesheet = client.get("/assets/site.css")
    script = client.get("/assets/site.js")
    hero_background = client.get("/assets/hero-background.webp")
    assert stylesheet.status_code == 200
    assert stylesheet.headers["content-type"].startswith("text/css")
    assert ".policy-layout" in stylesheet.text
    assert 'url("http' not in stylesheet.text
    assert 'url("/assets/hero-background.webp")' in stylesheet.text
    assert hero_background.status_code == 200
    assert hero_background.headers["content-type"].startswith("image/webp")
    assert hero_background.content[:4] == b"RIFF"
    assert hero_background.content[8:12] == b"WEBP"
    assert sha512_integrity(hero_background.content) == (
        "sha512-4k1u9o1s8EGw2Escm2o5X2e2a1KoXDfNh1mGn5h1deSHK6wTtykUeP9Y3Ax9s8Hm"
        "B44RxudosPSB7c0lob7Aaw=="
    )
    assert script.status_code == 200
    assert "application/javascript" in script.headers["content-type"]
    assert "data-service-status" in script.text
    assert "event.key === 'Escape'" in script.text
    assert ".catch(function ()" in script.text
    assert "navigator.clipboard" not in script.text


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/terms",
        "/privacy",
        "/licenses",
        "/components",
        "/missing-page",
    ],
)
def test_frontend_resources_use_sha512_integrity(client, path):
    html = client.get(path).text
    resources = re.findall(
        r'<(?:link|script)\b[^>]*(?:href|src)="([^"]+)"[^>]*'
        r'integrity="([^"]+)"[^>]*>',
        html,
    )
    assert resources
    for resource, integrity in resources:
        assert integrity.startswith("sha512-")
        response = client.get(resource)
        assert response.status_code == 200
        assert integrity == sha512_integrity(response.content)
    assert html.count('crossorigin="anonymous"') >= len(resources)


@pytest.mark.parametrize(
    "path", ["/", "/terms", "/privacy", "/licenses", "/components"]
)
def test_pages_expose_accessible_navigation_and_status(client, path):
    html = client.get(path).text
    assert 'aria-label="メインナビゲーション"' in html
    assert 'aria-controls="site-nav"' in html
    if path == "/":
        assert 'role="status" aria-live="polite" aria-atomic="true"' in html
        assert 'id="integration"' not in html
        assert 'data-copy-target' not in html
    else:
        assert 'data-status-message role="status" aria-live="polite"' in html


@pytest.mark.parametrize(
    "path", ["/", "/terms", "/privacy", "/licenses", "/components"]
)
def test_internal_page_links_resolve(client, path):
    html = client.get(path).text
    references = re.findall(r'(?:href|src)="([^"]*)"', html)
    for reference in references:
        if not reference.startswith("/") or reference.startswith("//"):
            continue
        target, _, fragment = reference.partition("#")
        target = target or path
        response = client.get(target)
        assert response.status_code < 400, f"{path} links to {reference}"
        if fragment and response.headers["content-type"].startswith("text/html"):
            assert re.search(
                rf'\bid=["\']{re.escape(fragment)}["\']', response.text
            ), f"{path} links to missing fragment {reference}"


def test_only_v2_sdk_route_is_exposed(client):
    response = client.get("/sdk/v2.js")
    assert response.status_code == 200
    assert "loadFont" not in response.text
    assert "document.currentScript" in response.text
    assert "options.baseUrl || defaultBaseUrl" in response.text
    assert client.get("/webfont-sdk.js").status_code == 404


def test_legacy_api_is_not_exposed(client):
    assert client.get("/api").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_rejects_unknown_origin(client):
    response = client.post(
        "/v2/subsets",
        headers={"Origin": "https://example.com"},
        json={"font": "zen-kaku-regular", "characters": "test"},
    )
    assert response.status_code == 403


def test_rejects_unknown_font(client):
    response = client.post(
        "/v2/subsets",
        json={"font": "unknown", "characters": "test"},
    )
    assert response.status_code == 400


def test_generates_and_reuses_woff2_subset(client):
    if not fonts_available():
        return
    payload = {"font": "zen-kaku-regular", "characters": "稼働情報ABC123"}
    headers = {"Origin": "http://localhost:8000"}

    first = client.post("/v2/subsets", headers=headers, json=payload)
    assert first.status_code == 200
    body = first.json()
    assert body["font"] == "zen-kaku-regular"
    assert body["unicodeRange"].startswith("U+")
    assert body["url"].startswith(f"{settings.public_base_url}/v2/fonts/")

    font = client.get(body["url"])
    assert font.status_code == 200
    assert font.content[:4] == b"wOF2"
    assert font.headers["cache-control"] == "public, max-age=31536000, immutable"

    second = client.post("/v2/subsets", headers=headers, json=payload)
    assert second.status_code == 200
    assert second.json()["hash"] == body["hash"]
    assert second.json()["cached"] is True
