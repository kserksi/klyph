from __future__ import annotations

import unicodedata


BASE_CHARACTERS = " "


def normalize_characters(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("characters must be a string")

    normalized = unicodedata.normalize("NFC", value)
    characters = set(BASE_CHARACTERS)

    for character in normalized:
        category = unicodedata.category(character)
        if character == " " or not category.startswith("C"):
            characters.add(character)

    return "".join(sorted(characters, key=ord))


def unicode_range(value: str) -> str:
    points = sorted({ord(character) for character in value})
    if not points:
        return ""

    ranges: list[str] = []
    start = previous = points[0]
    for point in points[1:]:
        if point == previous + 1:
            previous = point
            continue
        ranges.append(_format_range(start, previous))
        start = previous = point
    ranges.append(_format_range(start, previous))
    return ",".join(ranges)


def _format_range(start: int, end: int) -> str:
    if start == end:
        return f"U+{start:X}"
    return f"U+{start:X}-{end:X}"

