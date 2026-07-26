#!/usr/bin/env python3
"""Diagnostic en lecture seule d'un environnement BLDEMAT déployé."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "shared"))

from bl_core import database  # noqa: E402
from bl_core.config import get_settings  # noqa: E402

REQUIRED_TABLES = {
    "base_tiers",
    "base_desadv",
    "suivi_bl",
    "pieces_jointes_bl",
    "roles_utilisateurs",
    "audit_bl",
    "audit_evenements",
    "qualite_extraction",
    "notifications",
    "notification_livraisons",
    "job_executions",
    "schema_migrations",
}


def main() -> int:
    argparse.ArgumentParser().parse_args()
    settings = get_settings()
    status = database.healthcheck()
    frame = database.run(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = %(schema)s",
        {"schema": settings.pg_schema},
        fetch=True,
    )
    present = set(frame["table_name"].tolist()) if frame is not None else set()
    missing = sorted(REQUIRED_TABLES - present)
    result = {
        "environment": settings.environment,
        "schema": settings.pg_schema,
        "database": status,
        "image_backend": settings.image_backend,
        "volume_path": settings.volume_path,
        "missing_tables": missing,
        "status": "KO" if missing else "OK",
    }
    print(json.dumps(result, default=str, indent=2, ensure_ascii=False))
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
