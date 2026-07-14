from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .config import settings


@dataclass(frozen=True)
class FontSpec:
    id: str
    filename: str
    family: str
    weight: int
    style: str = "normal"

    @property
    def path(self) -> Path:
        return settings.font_dir / self.filename

    @property
    def version(self) -> str:
        return source_digest(self.path)[:12]


FONTS = {
    "zen-kaku-regular": FontSpec(
        "zen-kaku-regular", "ZenKakuGothicNew-Regular.ttf", "Zen Kaku Gothic New", 400
    ),
    "zen-maru-regular": FontSpec(
        "zen-maru-regular", "ZenMaruGothic-Regular.ttf", "Zen Maru Gothic", 400
    ),
    "zen-maru-bold": FontSpec(
        "zen-maru-bold", "ZenMaruGothic-Bold.ttf", "Zen Maru Gothic", 700
    ),
}

@lru_cache(maxsize=32)
def source_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def get_font(font_id: str) -> FontSpec:
    try:
        spec = FONTS[font_id]
    except KeyError as error:
        raise ValueError("unknown font") from error
    if not spec.path.is_file():
        raise FileNotFoundError(f"font file is missing: {spec.filename}")
    return spec
