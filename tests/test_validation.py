from __future__ import annotations

import pytest
from bl_core.config import reset_settings_cache
from bl_core.validation import normalize_bl_number, validate_pages


def test_bl_number_is_normalized():
    assert normalize_bl_number("  BL-2026   0001 ") == "BL-2026 0001"


@pytest.mark.parametrize("value", ["", "<script>", "A" * 81, "\n"])
def test_bl_number_rejects_unsafe_values(value):
    with pytest.raises(ValueError):
        normalize_bl_number(value)


def test_page_limits(monkeypatch):
    monkeypatch.setenv("BL_MAX_IMAGE_BYTES", "256000")
    monkeypatch.setenv("BL_MAX_TOTAL_BYTES", "300000")
    monkeypatch.setenv("BL_MAX_PAGES", "2")
    reset_settings_cache()
    result = validate_pages([b"a" * 100_000, b"b" * 120_000])
    assert result.count == 2
    assert result.total_bytes == 220_000
    with pytest.raises(ValueError, match="limite totale"):
        validate_pages([b"a" * 160_000, b"b" * 160_000])
    reset_settings_cache()
