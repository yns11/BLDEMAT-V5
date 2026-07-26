#!/usr/bin/env python3
"""Construit une archive déterministe et vérifie son intégrité."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
PREFIX = "BLDEMAT-V5-Professional"
EXCLUDED_PARTS = {
    ".git",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "dist",
}
EXCLUDED_NAMES = {".env", "deployment/bundle.env", "deployment/local.env"}
FIXED_TIME = (2026, 7, 25, 0, 0, 0)


def source_files() -> list[Path]:
    result = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        if any(part in EXCLUDED_PARTS for part in relative.parts):
            continue
        if str(relative) in EXCLUDED_NAMES or path.suffix in {".pyc", ".pyo"}:
            continue
        result.append(relative)
    return sorted(result)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def add_file(archive: zipfile.ZipFile, source: Path, target: str) -> None:
    info = zipfile.ZipInfo(target, date_time=FIXED_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    archive.writestr(info, source.read_bytes())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=DIST / "BLDEMAT-V5-Professional-ready-to-deploy.zip",
    )
    args = parser.parse_args()
    files = source_files()
    if not files:
        raise RuntimeError("Aucun fichier à empaqueter.")

    with tempfile.TemporaryDirectory(prefix="bldemat-release-") as temporary:
        staging = Path(temporary) / PREFIX
        for relative in files:
            destination = staging / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, destination)

        manifest = {
            "product": "BLDEMAT V5 Professional",
            "version": "5.0.0",
            "build_date": date.today().isoformat(),
            "python": ">=3.11,<3.13",
            "files": [
                {
                    "path": str(relative),
                    "size": (staging / relative).stat().st_size,
                    "sha256": digest(staging / relative),
                }
                for relative in files
            ],
        }
        manifest_path = staging / "RELEASE_MANIFEST.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        args.output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(args.output, "w") as archive:
            for path in sorted(staging.rglob("*")):
                if path.is_file():
                    add_file(
                        archive,
                        path,
                        f"{PREFIX}/{path.relative_to(staging).as_posix()}",
                    )

    with zipfile.ZipFile(args.output) as archive:
        bad = archive.testzip()
        names = archive.namelist()
    if bad:
        raise RuntimeError(f"CRC invalide dans l'archive : {bad}")
    if len(names) != len(set(names)):
        raise RuntimeError("L'archive contient des chemins dupliqués.")

    print(f"Archive : {args.output}")
    print(f"Fichiers : {len(names)}")
    print(f"Taille : {args.output.stat().st_size} octets")
    print(f"SHA-256 : {digest(args.output)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
