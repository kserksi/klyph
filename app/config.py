from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    font_dir: Path = Path(os.getenv("FONT_DIR", ROOT / "fonts"))
    cache_dir: Path = Path(os.getenv("FONT_CACHE_DIR", ROOT / "cache"))
    static_dir: Path = Path(os.getenv("FONT_STATIC_DIR", ROOT / "static"))
    public_base_url: str = os.getenv(
        "FONT_PUBLIC_BASE_URL", "http://localhost:8000"
    ).rstrip("/")
    max_request_bytes: int = int(os.getenv("FONT_MAX_REQUEST_BYTES", "65536"))
    max_characters: int = int(os.getenv("FONT_MAX_CHARACTERS", "8000"))
    generation_timeout: float = float(os.getenv("FONT_GENERATION_TIMEOUT", "20"))
    generation_workers: int = int(os.getenv("FONT_GENERATION_WORKERS", "2"))
    max_pending_generations: int = int(os.getenv("FONT_MAX_PENDING_GENERATIONS", "32"))
    max_cache_bytes: int = int(os.getenv("FONT_MAX_CACHE_BYTES", str(10 * 1024**3)))
    min_free_bytes: int = int(os.getenv("FONT_MIN_FREE_BYTES", str(256 * 1024**2)))
    cache_max_age_days: int = int(os.getenv("FONT_CACHE_MAX_AGE_DAYS", "30"))
    cache_cleanup_interval: float = float(
        os.getenv("FONT_CACHE_CLEANUP_INTERVAL", "86400")
    )
    shutdown_timeout: float = float(os.getenv("FONT_SHUTDOWN_TIMEOUT", "10"))
    log_level: str = os.getenv("FONT_LOG_LEVEL", "INFO").upper()
    allowed_origins: tuple[str, ...] = tuple(
        value.strip().rstrip("/")
        for value in os.getenv(
            "FONT_ALLOWED_ORIGINS",
            "http://localhost:8000,http://127.0.0.1:8000",
        ).split(",")
        if value.strip()
    )

    def __post_init__(self) -> None:
        positive_values = {
            "max_request_bytes": self.max_request_bytes,
            "max_characters": self.max_characters,
            "generation_timeout": self.generation_timeout,
            "generation_workers": self.generation_workers,
            "max_pending_generations": self.max_pending_generations,
            "max_cache_bytes": self.max_cache_bytes,
            "min_free_bytes": self.min_free_bytes,
            "cache_max_age_days": self.cache_max_age_days,
            "cache_cleanup_interval": self.cache_cleanup_interval,
            "shutdown_timeout": self.shutdown_timeout,
        }
        invalid = [name for name, value in positive_values.items() if value <= 0]
        if invalid:
            raise ValueError(f"settings must be positive: {', '.join(invalid)}")
        if self.max_pending_generations < self.generation_workers:
            raise ValueError("max_pending_generations must be at least generation_workers")

        public_url = urlparse(self.public_base_url)
        if public_url.scheme not in {"http", "https"} or not public_url.netloc:
            raise ValueError("FONT_PUBLIC_BASE_URL must be an absolute HTTP(S) URL")
        if (
            public_url.path not in {"", "/"}
            or public_url.params
            or public_url.query
            or public_url.fragment
            or public_url.username
        ):
            raise ValueError("FONT_PUBLIC_BASE_URL must not contain a path, query, or fragment")
        if (
            public_url.scheme == "http"
            and public_url.hostname not in {"localhost", "127.0.0.1", "::1"}
        ):
            raise ValueError("FONT_PUBLIC_BASE_URL must use HTTPS except on loopback")

        for origin in self.allowed_origins:
            parsed = urlparse(origin)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.netloc
                or parsed.path not in {"", "/"}
                or parsed.params
                or parsed.query
                or parsed.fragment
                or parsed.username
                or (
                    parsed.scheme == "http"
                    and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
                )
            ):
                raise ValueError(f"invalid allowed origin: {origin}")
        if self.log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("FONT_LOG_LEVEL is invalid")


settings = Settings()
