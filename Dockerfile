FROM python:3.14.6-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FONT_DIR=/app/fonts \
    FONT_CACHE_DIR=/app/cache \
    FONT_PUBLIC_BASE_URL=http://localhost:8000 \
    FONT_GENERATION_WORKERS=2 \
    FONT_MAX_PENDING_GENERATIONS=32 \
    FONT_MAX_CACHE_BYTES=10737418240 \
    FONT_MIN_FREE_BYTES=268435456

WORKDIR /app

COPY requirements.lock ./requirements.lock
RUN pip install --no-cache-dir --requirement requirements.lock

COPY app ./app
COPY static ./static
COPY fonts ./fonts

RUN mkdir -p /app/cache && useradd --system --uid 10001 fontsvc && chown -R fontsvc:fontsvc /app/cache

USER fontsvc
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/readyz', timeout=2).read()"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--limit-concurrency", "100", "--timeout-keep-alive", "5", "--no-access-log"]
