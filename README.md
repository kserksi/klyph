# Klyph

[English](README.md) · [简体中文](README.zh-CN.md) · [日本語](README.ja.md)

Repository: [github.com/kserksi/klyph](https://github.com/kserksi/klyph)

Klyph is a deterministic, self-hosted web-font subsetting service. It normalizes a requested character set, generates an immutable WOFF2 subset with FastAPI and FontTools, and serves it through a versioned API and a browser SDK. It has no required domain or hosting-provider dependency.

## Features

- Deterministic subsets keyed by font version, options, and normalized characters
- Process-isolated font generation with concurrency, queue, and timeout limits
- Immutable font URLs with long-lived browser and CDN caching
- Automatic removal of cache entries unused for more than 30 days
- Origin allowlist, request-size limits, security headers, and structured logs
- Health, readiness, legal, license, and open-source component pages

## Font assets

The source fonts come from the official Google Fonts GitHub repository and are pinned to exact commits:

```powershell
python scripts/download_fonts.py
```

The script records source metadata and SHA-256 digests in `fonts/sources.json`. Both font families include their SIL Open Font License 1.1 texts.

## Local development

```powershell
python -m venv .venv
.venv\Scripts\pip install -e ".[test]"
python scripts/download_fonts.py
.venv\Scripts\uvicorn app.main:app --reload
```

Run the test suite with:

```powershell
.venv\Scripts\python.exe -m pytest
```

## Docker

Download the fonts before building the image:

```powershell
python scripts/download_fonts.py
docker build -t klyph .
docker run --rm -p 8000:8000 `
  -e FONT_PUBLIC_BASE_URL=https://fonts.example.com `
  -e FONT_ALLOWED_ORIGINS=https://www.example.com `
  -v font-cache:/app/cache `
  klyph
```

The image is based on Python 3.14.6 slim, runs as a non-root user, and starts a single HTTP process. `/healthz` is the liveness endpoint. `/readyz` also verifies that required font files exist and the cache directory is writable. Runtime dependencies are pinned in `requirements.lock`.

## API v2

```http
POST /v2/subsets
Content-Type: application/json

{"font":"zen-kaku-regular","characters":"障害情報"}
```

The response contains an immutable WOFF2 URL versioned by the font version and normalized character hash.

Possible error responses:

- `400`: invalid font or character input
- `403`: browser origin is not allowed
- `413`: request body exceeds the configured limit
- `503`: generation queue is full, a lock timed out, or generation timed out
- `507`: cache capacity or minimum free-space threshold was reached

## Browser SDK

```html
<script defer src="https://fonts.example.com/sdk/v2.js"></script>
<script>
document.addEventListener('DOMContentLoaded', function () {
  WebFont.load({
    font: 'zen-kaku-regular',
    family: 'Zen Kaku Gothic New',
    selectors: ['.post-content', '.site-header']
  });
});
</script>
```

Use `WebFont.observe()` for debounced incremental loading when monitored content changes.

## Information pages

- `/`: service overview, live readiness, font specimens, and internal API summary
- `/terms`: terms of service
- `/privacy`: character data, logging, external service, and cache handling policy
- `/licenses`: font, artwork, and software licenses and credits
- `/components`: production open-source components and pinned versions

The pages share `/assets/site.css` and `/assets/site.js`. They use no cookies, local storage, or third-party analytics. FastAPI's interactive documentation and OpenAPI schema are disabled.

Search metadata is provided through `robots.txt`, `sitemap.xml`, canonical links, hreflang, Open Graph, Twitter Cards, and Schema.org JSON-LD. Machine endpoints return `X-Robots-Tag: noindex, nofollow`.

Regenerate the local brand assets on Windows after changing the visual identity:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/generate_brand_assets.ps1
```

## Configuration

| Environment variable | Default | Description |
| --- | ---: | --- |
| `FONT_PUBLIC_BASE_URL` | `http://localhost:8000` | Fixed public root used in API responses and rendered metadata |
| `FONT_ALLOWED_ORIGINS` | local port 8000 | Comma-separated origins allowed to call the generation endpoint |
| `FONT_MAX_REQUEST_BYTES` | `65536` | Maximum request-body size in bytes |
| `FONT_MAX_CHARACTERS` | `8000` | Maximum number of normalized unique characters |
| `FONT_GENERATION_TIMEOUT` | `20` | Total lock-wait and generation timeout in seconds |
| `FONT_GENERATION_WORKERS` | `2` | Maximum concurrent font-generation processes |
| `FONT_MAX_PENDING_GENERATIONS` | `32` | Maximum pending jobs for distinct character sets |
| `FONT_MAX_CACHE_BYTES` | `10737418240` | Maximum immutable font cache size (10 GiB) |
| `FONT_MIN_FREE_BYTES` | `268435456` | Free space reserved on the cache volume (256 MiB) |
| `FONT_CACHE_MAX_AGE_DAYS` | `30` | Delete a font after this many days without access |
| `FONT_CACHE_CLEANUP_INTERVAL` | `86400` | Cache cleanup interval in seconds (24 hours) |
| `FONT_SHUTDOWN_TIMEOUT` | `10` | Graceful shutdown timeout in seconds |
| `FONT_LOG_LEVEL` | `INFO` | Structured application log level |

Klyph writes single-line JSON logs to standard output. Logs include request IDs, font IDs, unique character counts, subset hashes, cache hits, output sizes, and durations. Raw character content is never logged.

## Production notes

- CORS and Origin checks are not authentication. Restrict the origin server to the edge proxy and protect `/v2/subsets` with method rules, per-client rate limits, and a global circuit breaker.
- Serve `/v2/fonts/*` through a long-lived CDN cache.
- Keep one HTTP process per origin instance. Each subset operation runs in an isolated child process and is terminated on timeout.
- Cached WOFF2 content remains immutable. Access markers track usage, and entries unused for more than 30 days are removed periodically.
- For multiple origin instances, replace the local cache with shared object storage and the filesystem generation lock with a distributed lock.
- Alert on `503`, `507`, generation failures, and generation latency.

## Licensing

Klyph's source code is licensed under the [Apache License 2.0](LICENSE). The bundled fonts are distributed separately under SIL Open Font License 1.1. See `fonts/OFL-kaku.txt`, `fonts/OFL-maru.txt`, and the `/licenses` page for attribution details.
