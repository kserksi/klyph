from __future__ import annotations

import base64
import hashlib
import re
import time
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from functools import lru_cache
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import settings
from .middleware import (
    RequestBodyLimitMiddleware,
    SECURITY_HEADERS,
    content_security_policy,
)
from .observability import logger, request_id_context
from .registry import FONTS, get_font
from .service import (
    CacheCapacityError,
    GenerationError,
    ServiceBusyError,
    SubsetResult,
    subset_service,
)


REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{8,64}$")
NON_INDEXABLE_PREFIXES = ("/assets/", "/healthz", "/readyz", "/sdk/", "/v2/")
MACHINE_ENDPOINT_PATHS = frozenset({"/healthz", "/readyz"})
MACHINE_ENDPOINT_PREFIXES = ("/assets/", "/sdk/", "/v2/")
HTML_ERROR_STATUSES = frozenset({403, 404, 500})
JSON_LD_PATTERN = re.compile(
    r'<script type="application/ld\+json">([\s\S]*?)</script>'
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await subset_service.start()
    logger.info("font service started", extra={"event": "service_started"})
    try:
        yield
    finally:
        await subset_service.close()
        logger.info("font service stopped", extra={"event": "service_stopped"})


app = FastAPI(
    title="Klyph",
    version="2.0.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)
app.add_middleware(RequestBodyLimitMiddleware, max_bytes=settings.max_request_bytes)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.allowed_origins),
    allow_credentials=False,
    allow_methods=["POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
    max_age=86400,
)


class SubsetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    font: str = Field(min_length=1, max_length=64)
    characters: str = Field(min_length=1)


def is_machine_endpoint(path: str) -> bool:
    return path in MACHINE_ENDPOINT_PATHS or path.startswith(MACHINE_ENDPOINT_PREFIXES)


@lru_cache(maxsize=len(HTML_ERROR_STATUSES))
def error_page_template(status_code: int) -> str:
    if status_code not in HTML_ERROR_STATUSES:
        raise ValueError("unsupported HTML error status")
    return (settings.static_dir / f"{status_code}.html").read_text(encoding="utf-8")


def error_page_response(request: Request, status_code: int) -> HTMLResponse:
    request_id = getattr(request.state, "request_id", uuid.uuid4().hex)
    timestamp = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    content = error_page_template(status_code).replace(
        "{{REQUEST_ID}}", request_id
    ).replace("{{TIMESTAMP}}", timestamp)
    headers = {
        **SECURITY_HEADERS,
        "Cache-Control": "no-store",
        "X-Request-ID": request_id,
        "X-Robots-Tag": "noindex, nofollow, noarchive",
    }
    return HTMLResponse(content, status_code=status_code, headers=headers)


@lru_cache(maxsize=8)
def public_text_asset(filename: str) -> str:
    template = (settings.static_dir / filename).read_text(encoding="utf-8")
    return template.replace("{{PUBLIC_BASE_URL}}", settings.public_base_url)


def public_html_response(filename: str, max_age: int) -> HTMLResponse:
    content = public_text_asset(filename)
    match = JSON_LD_PATTERN.search(content)
    hashes: tuple[str, ...] = ()
    if match is not None:
        digest = base64.b64encode(
            hashlib.sha256(match.group(1).encode("utf-8")).digest()
        ).decode("ascii")
        hashes = (f"sha256-{digest}",)
    return HTMLResponse(
        content,
        headers={
            "Cache-Control": f"public, max-age={max_age}",
            "Content-Security-Policy": content_security_policy(hashes),
        },
    )


@app.exception_handler(StarletteHTTPException)
async def http_error_page(
    request: Request, error: StarletteHTTPException
) -> Response:
    if error.status_code in {403, 404} and not is_machine_endpoint(request.url.path):
        return error_page_response(request, error.status_code)
    return JSONResponse(
        {"detail": error.detail},
        status_code=error.status_code,
        headers=error.headers,
    )


@app.exception_handler(Exception)
async def unhandled_error_page(request: Request, _: Exception) -> Response:
    if not is_machine_endpoint(request.url.path):
        return error_page_response(request, 500)
    request_id = getattr(request.state, "request_id", uuid.uuid4().hex)
    return JSONResponse(
        {"detail": "internal server error"},
        status_code=500,
        headers={
            **SECURITY_HEADERS,
            "Cache-Control": "no-store",
            "X-Request-ID": request_id,
            "X-Robots-Tag": "noindex, nofollow",
        },
    )


def origin_allowed(origin: str | None) -> bool:
    if not origin:
        return True
    try:
        parsed = urlparse(origin)
        return (
            parsed.scheme in {"http", "https"}
            and bool(parsed.hostname)
            and origin.rstrip("/") in settings.allowed_origins
        )
    except ValueError:
        return False


def require_origin(request: Request) -> str | None:
    origin = request.headers.get("origin")
    if not origin_allowed(origin):
        raise HTTPException(status_code=403, detail="origin is not allowed")
    return origin


def subset_payload(result: SubsetResult, font_id: str) -> dict[str, object]:
    font = get_font(font_id)
    return {
        "font": font.id,
        "family": font.family,
        "weight": font.weight,
        "style": font.style,
        "characters": result.characters,
        "unicodeRange": result.unicode_range,
        "hash": result.key,
        "url": (
            f"{settings.public_base_url}/v2/fonts/"
            f"{font.id}/{font.version}/{result.key}.woff2"
        ),
        "cached": result.cached,
    }


@app.middleware("http")
async def request_observability(request: Request, call_next):
    supplied_request_id = request.headers.get("x-request-id", "")
    request_id = (
        supplied_request_id
        if REQUEST_ID_PATTERN.fullmatch(supplied_request_id)
        else uuid.uuid4().hex
    )
    token = request_id_context.set(request_id)
    request.state.request_id = request_id
    started = time.monotonic()
    try:
        response = await call_next(request)
    except BaseException as error:
        logger.exception(
            "request failed",
            extra={
                "event": "request_failed",
                "method": request.method,
                "path": request.url.path,
                "duration_ms": round((time.monotonic() - started) * 1000, 2),
                "error_type": type(error).__name__,
            },
        )
        raise
    else:
        response.headers["X-Request-ID"] = request_id
        for header, value in SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        if request.url.path.startswith(NON_INDEXABLE_PREFIXES):
            response.headers.setdefault("X-Robots-Tag", "noindex, nofollow")
        logger.info(
            "request completed",
            extra={
                "event": "request_completed",
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round((time.monotonic() - started) * 1000, 2),
            },
        )
        return response
    finally:
        request_id_context.reset(token)


@app.get("/healthz")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
async def readiness() -> JSONResponse:
    missing_fonts = [spec.filename for spec in FONTS.values() if not spec.path.is_file()]
    ready, detail = subset_service.readiness()
    if missing_fonts:
        ready = False
        detail = "required font files are missing"
    status_code = 200 if ready else 503
    return JSONResponse(
        {"status": "ready" if ready else "not_ready", "detail": detail},
        status_code,
    )


@app.get("/")
async def home() -> HTMLResponse:
    return public_html_response("index.html", 300)


@app.get("/terms")
async def terms() -> HTMLResponse:
    return public_html_response("terms.html", 3600)


@app.get("/privacy")
async def privacy() -> HTMLResponse:
    return public_html_response("privacy.html", 3600)


@app.get("/licenses")
async def licenses() -> HTMLResponse:
    return public_html_response("licenses.html", 3600)


@app.get("/components")
async def components() -> HTMLResponse:
    return public_html_response("components.html", 3600)


@app.get("/robots.txt")
async def robots() -> Response:
    return Response(
        public_text_asset("robots.txt"),
        media_type="text/plain",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@app.get("/sitemap.xml")
async def sitemap() -> Response:
    return Response(
        public_text_asset("sitemap.xml"),
        media_type="application/xml",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@app.get("/site.webmanifest")
async def web_manifest() -> FileResponse:
    return FileResponse(
        settings.static_dir / "site.webmanifest",
        media_type="application/manifest+json",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.get("/favicon.svg")
async def favicon() -> FileResponse:
    return FileResponse(
        settings.static_dir / "favicon.svg",
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=604800"},
    )


@app.get("/apple-touch-icon.png")
async def apple_touch_icon() -> FileResponse:
    return FileResponse(
        settings.static_dir / "apple-touch-icon.png",
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=604800"},
    )


@app.get("/icon-192.png")
async def icon_192() -> FileResponse:
    return FileResponse(
        settings.static_dir / "icon-192.png",
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=604800"},
    )


@app.get("/icon-512.png")
async def icon_512() -> FileResponse:
    return FileResponse(
        settings.static_dir / "icon-512.png",
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=604800"},
    )


@app.get("/og-image.png")
async def open_graph_image() -> FileResponse:
    return FileResponse(
        settings.static_dir / "og-image.png",
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=604800"},
    )


@app.get("/assets/site.css")
async def site_styles() -> FileResponse:
    return FileResponse(
        settings.static_dir / "site.css",
        media_type="text/css",
        headers={"Cache-Control": "public, max-age=604800"},
    )


@app.get("/assets/site.js")
async def site_script() -> FileResponse:
    return FileResponse(
        settings.static_dir / "site.js",
        media_type="application/javascript",
        headers={"Cache-Control": "public, max-age=604800"},
    )


@app.options("/v2/subsets")
async def subset_options(request: Request) -> Response:
    origin = require_origin(request)
    response = Response(status_code=204)
    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
    response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Request-ID"
    response.headers["Access-Control-Max-Age"] = "86400"
    return response


@app.post("/v2/subsets")
async def create_subset(payload: SubsetRequest, request: Request) -> JSONResponse:
    origin = require_origin(request)
    try:
        font = get_font(payload.font)
        result = await subset_service.resolve(font, payload.characters)
    except (ValueError, FileNotFoundError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except (TimeoutError, ServiceBusyError) as error:
        raise HTTPException(
            status_code=503,
            detail=str(error),
            headers={"Retry-After": "1"},
        ) from error
    except CacheCapacityError as error:
        raise HTTPException(status_code=507, detail=str(error)) from error
    except GenerationError as error:
        raise HTTPException(status_code=500, detail="font generation failed") from error

    response = JSONResponse(subset_payload(result, font.id))
    response.headers["Cache-Control"] = "no-store"
    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
    return response


@app.get("/v2/fonts/{font_id}/{version}/{key}.woff2")
async def get_subset(font_id: str, version: str, key: str) -> FileResponse:
    try:
        font = get_font(font_id)
    except (ValueError, FileNotFoundError) as error:
        raise HTTPException(status_code=404, detail="font not found") from error
    if version != font.version or len(key) != 64 or any(c not in "0123456789abcdef" for c in key):
        raise HTTPException(status_code=404, detail="font not found")
    path = subset_service.path_for(font, key)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="font not found")
    subset_service.record_access(path)
    return FileResponse(
        path,
        media_type="font/woff2",
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "ETag": f'"{key}"',
            "Access-Control-Allow-Origin": "*",
            "Cross-Origin-Resource-Policy": "cross-origin",
        },
    )


@app.get("/sdk/v2.js")
async def sdk() -> FileResponse:
    return FileResponse(
        settings.static_dir / "webfont-sdk.js",
        media_type="application/javascript",
        headers={"Cache-Control": "public, max-age=604800"},
    )
