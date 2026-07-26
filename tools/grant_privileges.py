#!/usr/bin/env python3
"""Applique les privilèges minimaux aux service principals BLDEMAT."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "shared"))

from bl_core import database  # noqa: E402
from bl_core.config import get_settings  # noqa: E402

ROLE_RE = re.compile(r"^[A-Za-z0-9_.:@+\-]{3,200}$")


def role(value: str) -> str:
    if not ROLE_RE.fullmatch(value):
        raise argparse.ArgumentTypeError("Identifiant de rôle PostgreSQL invalide.")
    return value


def execute_for(tx, principal: str, statements: list[str]) -> None:
    schema = sql.Identifier(get_settings().pg_schema)
    role_id = sql.Identifier(principal)
    for template in statements:
        tx.execute(
            sql.SQL(template).format(schema=schema, role=role_id)
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--creation-role", required=True, type=role)
    parser.add_argument("--admin-role", required=True, type=role)
    parser.add_argument("--jobs-role", required=True, type=role)
    args = parser.parse_args()

    current_db = database.run("SELECT current_database() AS name", fetch=True)["name"].iloc[0]
    common = [
        "REVOKE CREATE ON SCHEMA {schema} FROM {role}",
        "GRANT USAGE ON SCHEMA {schema} TO {role}",
    ]
    creation = common + [
        "GRANT SELECT ON {schema}.base_tiers, {schema}.base_desadv, "
        "{schema}.gestionnaires, {schema}.portefeuilles, {schema}.quais, "
        "{schema}.adresses, {schema}.sites_logistiques, {schema}.pla, "
        "{schema}.roles_utilisateurs TO {role}",
        "GRANT SELECT, INSERT ON {schema}.suivi_bl, {schema}.pieces_jointes_bl TO {role}",
        "GRANT UPDATE (document_statut, modifie_par, modifie_le, version) "
        "ON {schema}.suivi_bl TO {role}",
        "GRANT SELECT, INSERT ON {schema}.audit_bl, {schema}.qualite_extraction TO {role}",
        "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA {schema} TO {role}",
    ]
    admin = common + [
        "GRANT SELECT, INSERT, UPDATE, DELETE ON {schema}.base_tiers, "
        "{schema}.base_desadv, {schema}.gestionnaires, {schema}.portefeuilles, "
        "{schema}.quais, {schema}.adresses, {schema}.sites_logistiques, "
        "{schema}.pla, {schema}.roles_utilisateurs, {schema}.suivi_bl, "
        "{schema}.ecrans_utilisateur, {schema}.notifications, "
        "{schema}.notification_canaux, {schema}.notification_livraisons TO {role}",
        "GRANT SELECT ON {schema}.pieces_jointes_bl, {schema}.qualite_extraction, "
        "{schema}.job_executions, {schema}.v_rapprochement_bl_desadv TO {role}",
        "GRANT SELECT, INSERT ON {schema}.audit_bl, {schema}.audit_evenements TO {role}",
        "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA {schema} TO {role}",
    ]
    jobs = common + [
        "GRANT SELECT, INSERT, UPDATE ON {schema}.base_tiers, {schema}.base_desadv, "
        "{schema}.suivi_bl, {schema}.notification_livraisons, "
        "{schema}.job_executions TO {role}",
        "GRANT INSERT ON {schema}.audit_bl TO {role}",
        "GRANT SELECT ON {schema}.notifications, {schema}.notification_canaux TO {role}",
        "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA {schema} TO {role}",
    ]

    with database.transaction() as tx:
        for principal in (args.creation_role, args.admin_role, args.jobs_role):
            tx.execute(
                sql.SQL("REVOKE CREATE ON DATABASE {} FROM {}").format(
                    sql.Identifier(current_db), sql.Identifier(principal)
                )
            )
        execute_for(tx, args.creation_role, creation)
        execute_for(tx, args.admin_role, admin)
        execute_for(tx, args.jobs_role, jobs)
    print("Privilèges appliqués.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
