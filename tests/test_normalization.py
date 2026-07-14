from app.normalization import normalize_characters, unicode_range


def test_normalization_is_deterministic_and_removes_controls():
    assert normalize_characters("BAA\nＡB") == " ABＡ"
    assert normalize_characters("e\u0301é") == " é"


def test_unicode_range_compacts_adjacent_points():
    assert unicode_range(" ABC") == "U+20,U+41-43"

