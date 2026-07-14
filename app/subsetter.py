from __future__ import annotations

import os
from multiprocessing.connection import Connection
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont


OPTIONS_VERSION = "v2"


def build_subset(source: str, characters: str, destination: str) -> int:
    source_path = Path(source)
    destination_path = Path(destination)
    temporary_path = destination_path.with_suffix(destination_path.suffix + f".{os.getpid()}.tmp")

    options = subset.Options()
    options.flavor = "woff2"
    options.layout_features = ["*"]
    options.name_IDs = [0, 1, 2, 3, 4, 5, 6]
    options.name_legacy = True
    options.name_languages = [0x409, 0x411]
    options.notdef_glyph = True
    options.notdef_outline = True
    options.recommended_glyphs = True
    options.recalc_average_width = True
    options.recalc_timestamp = False
    options.canonical_order = True

    try:
        font = TTFont(source_path, recalcTimestamp=False, lazy=False)
        try:
            worker = subset.Subsetter(options=options)
            worker.populate(text=characters)
            worker.subset(font)
            font.flavor = "woff2"
            font.save(temporary_path)
        finally:
            font.close()

        _validate_woff2(temporary_path)
        os.replace(temporary_path, destination_path)
        return destination_path.stat().st_size
    finally:
        temporary_path.unlink(missing_ok=True)


def build_subset_worker(
    source: str, characters: str, destination: str, connection: Connection
) -> None:
    try:
        size = build_subset(source, characters, destination)
        result = (True, size, "")
    except BaseException as error:
        result = (False, 0, type(error).__name__)
    finally:
        try:
            connection.send(result)
        except (BrokenPipeError, EOFError, OSError):
            pass
        finally:
            connection.close()


def _validate_woff2(path: Path) -> None:
    if path.stat().st_size < 64:
        raise ValueError("generated font is unexpectedly small")
    with path.open("rb") as stream:
        if stream.read(4) != b"wOF2":
            raise ValueError("generated file is not WOFF2")
    font = TTFont(path, lazy=True)
    font.close()
