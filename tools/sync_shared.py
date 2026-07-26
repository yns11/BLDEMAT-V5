#!/usr/bin/env python3
"""Synchronise le cœur partagé dans les deux sources Databricks Apps."""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "shared" / "bl_core"
TARGETS = [
    ROOT / "src" / "app_creation" / "bl_core",
    ROOT / "src" / "app_administration" / "bl_core",
]


def main() -> int:
    sources = sorted(SOURCE.glob("*.py"))
    if not sources:
        raise RuntimeError(f"Aucun module trouvé dans {SOURCE}")
    for target in TARGETS:
        target.mkdir(parents=True, exist_ok=True)
        for stale in target.glob("*.py"):
            stale.unlink()
        for source in sources:
            shutil.copy2(source, target / source.name)
        print(f"{len(sources)} modules synchronisés vers {target.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
