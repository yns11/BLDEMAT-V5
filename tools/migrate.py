#!/usr/bin/env python3
"""Applique les migrations SQL BLDEMAT avec verrou et contrôles de checksum."""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "shared"))

from bl_core import database  # noqa: E402
from bl_core.config import get_settings  # noqa: E402

MIGRATION_RE = re.compile(r"^V(?P<version>\d{3})__(?P<name>[a-z0-9_]+)\.sql$")


def statements(sql: str) -> list[str]:
    """Séparateur suffisant pour les migrations du projet (sans blocs PL/pgSQL)."""
    return [part.strip() for part in sql.split(";") if part.strip()]


def migrations() -> list[tuple[str, str, Path, str]]:
    result = []
    for path in sorted((ROOT / "sql" / "migrations").glob("V*.sql")):
        match = MIGRATION_RE.fullmatch(path.name)
        if not match:
            raise RuntimeError(f"Nom de migration invalide : {path.name}")
        content = path.read_text(encoding="utf-8")
        checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
        result.append((match.group("version"), match.group("name"), path, checksum))
    if not result:
        raise RuntimeError("Aucune migration trouvée.")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--no-baseline-existing",
        action="store_true",
        help="Exécute V001 même si une table V4 est détectée.",
    )
    args = parser.parse_args()

    settings = get_settings()
    schema = settings.pg_schema
    items = migrations()
    if args.dry_run:
        for version, name, path, checksum in items:
            print(f"V{version} {name} {checksum[:12]} {path.relative_to(ROOT)}")
        return 0

    with database.transaction() as tx:
        tx.execute("SELECT pg_advisory_xact_lock(hashtext(%(key)s))", {"key": f"bldemat:{schema}"})
        tx.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
        tx.execute(
            f"CREATE TABLE IF NOT EXISTS {schema}.schema_migrations ("
            "version TEXT PRIMARY KEY, name TEXT NOT NULL, checksum TEXT NOT NULL, "
            "applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
        existing = tx.fetch_one(
            "SELECT to_regclass(%(table)s) IS NOT NULL AS present",
            {"table": f"{schema}.suivi_bl"},
        )
        applied_df = tx.fetch_dataframe(
            f"SELECT version, checksum FROM {schema}.schema_migrations"
        )
        applied = dict(zip(applied_df.get("version", []), applied_df.get("checksum", []), strict=False))

        first_version, first_name, _, first_checksum = items[0]
        if (
            existing
            and existing["present"]
            and not applied
            and not args.no_baseline_existing
        ):
            tx.execute(
                f"INSERT INTO {schema}.schema_migrations (version, name, checksum) "
                "VALUES (%(v)s, %(n)s, %(c)s)",
                {"v": first_version, "n": first_name + "_baseline_existing", "c": first_checksum},
            )
            applied[first_version] = first_checksum
            print(f"V{first_version} marquée comme baseline d'une installation existante.")

    for version, name, path, checksum in items:
        if version in applied:
            if applied[version] != checksum:
                raise RuntimeError(
                    f"Checksum différent pour V{version}. "
                    "Une migration appliquée ne doit jamais être modifiée."
                )
            print(f"V{version} déjà appliquée.")
            continue
        sql = path.read_text(encoding="utf-8").replace("{{schema}}", schema)
        with database.transaction() as tx:
            tx.execute("SELECT pg_advisory_xact_lock(hashtext(%(key)s))", {"key": f"bldemat:{schema}"})
            for statement in statements(sql):
                tx.execute(statement)
            tx.execute(
                f"INSERT INTO {schema}.schema_migrations (version, name, checksum) "
                "VALUES (%(v)s, %(n)s, %(c)s)",
                {"v": version, "n": name, "c": checksum},
            )
        print(f"V{version} appliquée : {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
