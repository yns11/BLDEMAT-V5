"""Dispatcher outbox par canal avec verrou, backoff et dead-letter."""

from __future__ import annotations

import argparse
import json
import logging
import urllib.request
import uuid
from datetime import datetime, timezone

from common import configure_logging, json_metrics, lakebase_connection
from databricks.sdk import WorkspaceClient

logger = logging.getLogger("bl.jobs.notifications")


def arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pg-host", required=True)
    parser.add_argument("--pg-database", required=True)
    parser.add_argument("--pg-schema", required=True)
    parser.add_argument("--lakebase-endpoint", required=True)
    parser.add_argument("--pg-user", required=True)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--max-attempts", type=int, default=8)
    return parser.parse_args()


def post_json(url: str, payload: dict, idempotency_key: str, timeout: int) -> None:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Idempotency-Key": idempotency_key,
            "User-Agent": "BLDEMAT/5",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if not 200 <= response.status < 300:
            raise RuntimeError(f"HTTP {response.status}")


def payload_for(row: dict) -> dict:
    base = {
        "event_id": row["notification_id"],
        "idempotency_key": row["idempotency_key"],
        "numero_bl": row["numero_bl"],
        "type_notif": row["type_notif"],
        "message": row["message"],
        "cree_le": str(row["cree_le"]),
        "cree_par": row["cree_par"],
    }
    if row["type_canal"] == "TEAMS":
        return {
            "@type": "MessageCard",
            "@context": "https://schema.org/extensions",
            "themeColor": "43B02A",
            "summary": f"BL {row['numero_bl']} : {row['type_notif']}",
            "sections": [{"activityTitle": "✅ Mise à jour BL", "text": row["message"]}],
            "metadata": base,
        }
    return base


def main() -> None:
    configure_logging()
    args = arguments()
    workspace = WorkspaceClient()
    run_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc)
    metrics = {"claimed": 0, "sent": 0, "failed": 0, "dead_letter": 0}

    with lakebase_connection(
        workspace,
        endpoint=args.lakebase_endpoint,
        host=args.pg_host,
        database=args.pg_database,
        user=args.pg_user,
    ) as connection:
        with connection.transaction(), connection.cursor() as cursor:
            cursor.execute(
                f"INSERT INTO {args.pg_schema}.job_executions "
                "(job_name, run_id, statut, started_at) "
                "VALUES ('dispatch_notifications', %s, 'STARTED', %s) RETURNING id",
                (run_id, started_at),
            )
            execution_id = cursor.fetchone()[0]
            cursor.execute(
                f"UPDATE {args.pg_schema}.notification_livraisons "
                "SET statut = 'ECHEC', verrouille_jusqua = NULL, "
                "prochaine_tentative_le = now(), "
                "derniere_erreur = coalesce(derniere_erreur, 'Verrou expiré après interruption') "
                "WHERE statut = 'EN_COURS' AND verrouille_jusqua < now()"
            )
            cursor.execute(
                f"""
                WITH candidates AS (
                  SELECT l.notification_id, l.canal
                  FROM {args.pg_schema}.notification_livraisons l
                  JOIN {args.pg_schema}.notification_canaux c ON c.code = l.canal
                  WHERE c.actif = true
                    AND l.statut IN ('EN_ATTENTE', 'ECHEC')
                    AND coalesce(l.prochaine_tentative_le, now()) <= now()
                    AND coalesce(l.verrouille_jusqua, '-infinity') < now()
                  ORDER BY l.prochaine_tentative_le NULLS FIRST, l.notification_id
                  FOR UPDATE OF l SKIP LOCKED
                  LIMIT %s
                )
                UPDATE {args.pg_schema}.notification_livraisons l
                SET statut = 'EN_COURS', verrouille_jusqua = now() + interval '5 minutes'
                FROM candidates c
                WHERE l.notification_id = c.notification_id AND l.canal = c.canal
                RETURNING l.notification_id, l.canal, l.idempotency_key, l.tentatives
                """,
                (args.batch_size,),
            )
            claimed = cursor.fetchall()
        metrics["claimed"] = len(claimed)

        for notification_id, canal, idempotency_key, attempts in claimed:
            try:
                with connection.transaction(), connection.cursor() as cursor:
                    cursor.execute(
                        f"""
                        SELECT n.id AS notification_id, n.type_notif, n.numero_bl,
                               n.message, n.cree_le, n.cree_par,
                               l.idempotency_key, c.type_canal, c.secret_scope,
                               c.secret_key, c.timeout_secondes
                        FROM {args.pg_schema}.notifications n
                        JOIN {args.pg_schema}.notification_livraisons l
                          ON l.notification_id = n.id
                        JOIN {args.pg_schema}.notification_canaux c ON c.code = l.canal
                        WHERE n.id = %s AND l.canal = %s
                        """,
                        (notification_id, canal),
                    )
                    columns = [item.name for item in cursor.description]
                    row = dict(zip(columns, cursor.fetchone(), strict=False))
                secret = workspace.secrets.get_secret(
                    scope=row["secret_scope"], key=row["secret_key"]
                ).value
                post_json(
                    secret,
                    payload_for(row),
                    idempotency_key,
                    int(row["timeout_secondes"]),
                )
                with connection.transaction(), connection.cursor() as cursor:
                    cursor.execute(
                        f"UPDATE {args.pg_schema}.notification_livraisons "
                        "SET statut = 'ENVOYEE', tentatives = tentatives + 1, "
                        "envoyee_le = now(), verrouille_jusqua = NULL, "
                        "prochaine_tentative_le = NULL, derniere_erreur = NULL "
                        "WHERE notification_id = %s AND canal = %s",
                        (notification_id, canal),
                    )
                metrics["sent"] += 1
            except Exception as exc:
                next_attempt = int(attempts) + 1
                dead = next_attempt >= args.max_attempts
                with connection.transaction(), connection.cursor() as cursor:
                    cursor.execute(
                        f"UPDATE {args.pg_schema}.notification_livraisons "
                        "SET statut = %s, tentatives = %s, verrouille_jusqua = NULL, "
                        "prochaine_tentative_le = CASE WHEN %s THEN NULL ELSE "
                        "now() + make_interval(mins => LEAST(360, power(2, %s)::int)) END, "
                        "derniere_erreur = %s "
                        "WHERE notification_id = %s AND canal = %s",
                        (
                            "DEAD_LETTER" if dead else "ECHEC",
                            next_attempt,
                            dead,
                            next_attempt,
                            str(exc)[:2000],
                            notification_id,
                            canal,
                        ),
                    )
                metrics["dead_letter" if dead else "failed"] += 1
                logger.exception("Livraison %s/%s en échec", notification_id, canal)

        with connection.transaction(), connection.cursor() as cursor:
            cursor.execute(
                f"UPDATE {args.pg_schema}.job_executions "
                "SET statut = 'SUCCEEDED', finished_at = now(), metrics = %s::jsonb "
                "WHERE id = %s",
                (json_metrics(**metrics), execution_id),
            )
    logger.info("Dispatch terminé : %s", json_metrics(**metrics))


if __name__ == "__main__":
    main()
