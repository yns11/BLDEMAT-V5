"""Utilitaires communs aux tâches Lakeflow BLDEMAT."""

from __future__ import annotations

import json
import logging
import sys
from contextlib import contextmanager
from typing import Iterator

import psycopg
from databricks.sdk import WorkspaceClient


def configure_logging() -> None:
    logging.basicConfig(
        stream=sys.stdout,
        level=logging.INFO,
        format='{"ts":"%(asctime)s","level":"%(levelname)s",'
        '"logger":"%(name)s","message":"%(message)s"}',
    )


def endpoint_token(workspace: WorkspaceClient, endpoint: str) -> str:
    return workspace.postgres.generate_database_credential(endpoint=endpoint).token


@contextmanager
def lakebase_connection(
    workspace: WorkspaceClient,
    *,
    endpoint: str,
    host: str,
    database: str,
    user: str,
) -> Iterator[psycopg.Connection]:
    connection = psycopg.connect(
        host=host,
        port=5432,
        dbname=database,
        user=user,
        password=endpoint_token(workspace, endpoint),
        sslmode="require",
        application_name="bldemat-jobs",
        connect_timeout=20,
    )
    try:
        yield connection
    finally:
        connection.close()


def json_metrics(**values) -> str:
    return json.dumps(values, default=str, ensure_ascii=False)
