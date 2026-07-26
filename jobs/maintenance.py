"""Maintenance quotidienne : brouillons interrompus et jobs orphelins."""

from __future__ import annotations

import argparse
import logging
import re
import uuid
from datetime import datetime, timezone

from common import configure_logging, json_metrics, lakebase_connection
from databricks.sdk import WorkspaceClient

logger = logging.getLogger("bl.jobs.maintenance")
IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pg-host", required=True)
    parser.add_argument("--pg-database", required=True)
    parser.add_argument("--pg-schema", required=True)
    parser.add_argument("--lakebase-endpoint", required=True)
    parser.add_argument("--pg-user", required=True)
    parser.add_argument("--draft-hours", type=int, default=24)
    parser.add_argument("--stale-job-hours", type=int, default=6)
    args = parser.parse_args()
    if not IDENTIFIER.fullmatch(args.pg_schema):
        parser.error("--pg-schema contient un identifiant invalide")
    if not 1 <= args.draft_hours <= 168:
        parser.error("--draft-hours doit être compris entre 1 et 168")
    if not 1 <= args.stale_job_hours <= 48:
        parser.error("--stale-job-hours doit être compris entre 1 et 48")
    return args


def main() -> None:
    configure_logging()
    args = arguments()
    workspace = WorkspaceClient()
    run_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc)
    metrics = {"drafts_marked_error": 0, "stale_jobs_closed": 0}

    with lakebase_connection(
        workspace,
        endpoint=args.lakebase_endpoint,
        host=args.pg_host,
        database=args.pg_database,
        user=args.pg_user,
    ) as connection:
        try:
            with connection.transaction(), connection.cursor() as cursor:
                cursor.execute(
                    f"INSERT INTO {args.pg_schema}.job_executions "
                    "(job_name, run_id, statut, started_at) "
                    "VALUES ('maintenance', %s, 'STARTED', %s) RETURNING id",
                    (run_id, started_at),
                )
                execution_id = cursor.fetchone()[0]
                cursor.execute(
                    f"""
                    WITH marked AS (
                      UPDATE {args.pg_schema}.suivi_bl
                      SET document_statut = 'ERREUR',
                          modifie_par = 'job:maintenance',
                          modifie_le = now(),
                          version = version + 1
                      WHERE document_statut = 'BROUILLON'
                        AND saisie_le < now() - make_interval(hours => %s)
                      RETURNING id_bl
                    )
                    INSERT INTO {args.pg_schema}.audit_bl
                      (id_bl, evenement, valeur_apres, modifie_par)
                    SELECT id_bl, 'BROUILLON_EXPIRE', 'ERREUR', 'job:maintenance'
                    FROM marked
                    """,
                    (args.draft_hours,),
                )
                metrics["drafts_marked_error"] = cursor.rowcount
                cursor.execute(
                    f"UPDATE {args.pg_schema}.job_executions "
                    "SET statut = 'FAILED', finished_at = now(), "
                    "erreur = coalesce(erreur, 'Exécution déclarée orpheline par maintenance') "
                    "WHERE statut = 'STARTED' AND id <> %s "
                    "AND started_at < now() - make_interval(hours => %s)",
                    (execution_id, args.stale_job_hours),
                )
                metrics["stale_jobs_closed"] = cursor.rowcount
                cursor.execute(
                    f"UPDATE {args.pg_schema}.job_executions "
                    "SET statut = 'SUCCEEDED', finished_at = now(), metrics = %s::jsonb "
                    "WHERE id = %s",
                    (json_metrics(**metrics), execution_id),
                )
        except Exception as exc:
            logger.exception("Maintenance en échec")
            with connection.transaction(), connection.cursor() as cursor:
                cursor.execute(
                    f"INSERT INTO {args.pg_schema}.job_executions "
                    "(job_name, run_id, statut, started_at, finished_at, erreur) "
                    "VALUES ('maintenance', %s, 'FAILED', %s, now(), %s)",
                    (run_id, started_at, str(exc)[:4000]),
                )
            raise
    logger.info("Maintenance terminée : %s", json_metrics(**metrics))


if __name__ == "__main__":
    main()
