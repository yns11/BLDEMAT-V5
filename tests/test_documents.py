from __future__ import annotations

import io

from bl_core import images, pdf_bl
from bl_core.config import reset_settings_cache
from bl_core.storage import VolumeStore
from PIL import Image, ImageDraw


def sample_jpeg() -> bytes:
    image = Image.new("RGB", (800, 1100), "white")
    drawing = ImageDraw.Draw(image)
    drawing.rectangle((80, 70, 720, 1030), outline="black", width=8)
    drawing.text((130, 150), "BL-2026-TEST", fill="black")
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=90)
    return buffer.getvalue()


def test_scan_pipeline_outputs_bounded_jpeg(monkeypatch):
    monkeypatch.setenv("BL_MAX_IMAGE_BYTES", "256000")
    reset_settings_cache()
    scanner = getattr(images.scanner_document, "__wrapped__", images.scanner_document)
    output, _corrected = scanner(
        sample_jpeg(), mode="Gris réhaussé", corriger_perspective=False
    )
    assert output.startswith(b"\xff\xd8")
    assert len(output) <= 256_000
    reset_settings_cache()


def test_pdf_export_is_valid():
    output = pdf_bl.generer_pdf_bl(
        [("Numéro de BL", "BL-2026-TEST")],
        [sample_jpeg()],
        "BL BL-2026-TEST",
    )
    assert output.startswith(b"%PDF-")
    assert len(output) > 1_000


def test_volume_store_rejects_foreign_uri():
    store = VolumeStore("/Volumes/main/bldemat/documents")
    try:
        store.get("/Volumes/other/schema/documents/file.jpg")
    except ValueError as exc:
        assert "hors du volume" in str(exc)
    else:
        raise AssertionError("Une URI hors volume aurait dû être refusée.")


def test_volume_upload_uses_supported_files_api(monkeypatch):
    calls = {}

    class FakeFiles:
        def create_directory(self, path):
            calls["directory"] = path

        def upload(self, path, contents, *, overwrite=None):
            calls["upload"] = (path, contents.read(), overwrite)

    class FakeClient:
        files = FakeFiles()

    monkeypatch.setattr(VolumeStore, "_client", staticmethod(lambda: FakeClient()))
    store = VolumeStore("/Volumes/main/bldemat/documents")
    stored = store.put("id-bl", 0, "id-photo", b"jpeg")
    assert calls["directory"].endswith("/bl/id-bl")
    assert calls["upload"][1:] == (b"jpeg", False)
    assert stored.size_bytes == 4
