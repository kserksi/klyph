from __future__ import annotations

import hashlib
import json
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
FONT_DIR = ROOT / "fonts"

SOURCES = {
    "kaku": {
        "repository": "googlefonts/zen-kakugothic",
        "commit": "2705757e17e42954f3acbdf921ac0ae24d1270cd",
        "files": ["ZenKakuGothicNew-Regular.ttf"],
    },
    "maru": {
        "repository": "googlefonts/zen-marugothic",
        "commit": "553c872b216d1290e2902a466edcdc9682f0df6a",
        "files": ["ZenMaruGothic-Regular.ttf", "ZenMaruGothic-Bold.ttf"],
    },
}


def download(url: str, destination: Path) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "Klyph/2"})
    digest = hashlib.sha256()
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with urllib.request.urlopen(request, timeout=60) as response, temporary.open("wb") as output:
        while chunk := response.read(1024 * 1024):
            digest.update(chunk)
            output.write(chunk)
    temporary.replace(destination)
    return digest.hexdigest()


def main() -> None:
    FONT_DIR.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, object] = {"sources": SOURCES, "files": {}}

    for source in SOURCES.values():
        repository = source["repository"]
        commit = source["commit"]
        for filename in source["files"]:
            url = f"https://raw.githubusercontent.com/{repository}/{commit}/fonts/ttf/{filename}"
            manifest["files"][filename] = {"url": url, "sha256": download(url, FONT_DIR / filename)}

        license_url = f"https://raw.githubusercontent.com/{repository}/{commit}/OFL.txt"
        license_name = "OFL-kaku.txt" if source is SOURCES["kaku"] else "OFL-maru.txt"
        manifest["files"][license_name] = {
            "url": license_url,
            "sha256": download(license_url, FONT_DIR / license_name),
        }

    (FONT_DIR / "sources.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
