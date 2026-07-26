"""Configuration centralisée et validée de BLDEMAT.

La solution ne contient aucune valeur propre à un environnement. Les
identifiants de ressources Databricks sont injectés par le bundle et les
secrets par les ressources d'application. Une configuration incohérente
échoue au démarrage, avant toute action métier.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from functools import lru_cache

_SCHEMA_RE = re.compile(r"^[a-z_][a-z0-9_]*$")
_ENVIRONMENTS = {"local", "dev", "rec", "prod"}
_RBAC_MODES = {"strict", "disabled"}
_IMAGE_BACKENDS = {"volume", "database"}


def _int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError as exc:
        raise RuntimeError(f"{name} doit être un entier.") from exc
    if not minimum <= value <= maximum:
        raise RuntimeError(f"{name} doit être compris entre {minimum} et {maximum}.")
    return value


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, str(default)).strip().lower()
    if raw in {"1", "true", "yes", "oui"}:
        return True
    if raw in {"0", "false", "no", "non"}:
        return False
    raise RuntimeError(f"{name} doit valoir true ou false.")


def _csv(name: str) -> tuple[str, ...]:
    return tuple(
        value.strip().lower()
        for value in os.environ.get(name, "").split(",")
        if value.strip()
    )


@dataclass(frozen=True)
class Settings:
    environment: str
    pg_schema: str
    timezone: str
    page_size_default: int
    max_image_bytes: int
    max_total_bytes: int
    max_dimension_px: int
    max_pages: int
    image_backend: str
    volume_path: str
    rbac_mode: str
    bootstrap_admins: tuple[str, ...]
    optimistic_locking: bool
    database_pool_min: int
    database_pool_max: int
    database_pool_lifetime_s: int
    database_connect_timeout_s: int
    notification_max_attempts: int
    notification_batch_size: int
    llm_endpoint: str
    llm_prompt_version: str

    @property
    def is_production(self) -> bool:
        return self.environment == "prod"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    environment = os.environ.get("BL_ENVIRONMENT", "local").strip().lower()
    if environment not in _ENVIRONMENTS:
        raise RuntimeError(
            f"BL_ENVIRONMENT invalide : {environment!r}. "
            f"Valeurs admises : {sorted(_ENVIRONMENTS)}."
        )

    schema = os.environ.get("BL_PG_SCHEMA", "bl_demat").strip()
    if not _SCHEMA_RE.fullmatch(schema):
        raise RuntimeError("BL_PG_SCHEMA doit être un identifiant PostgreSQL simple.")

    rbac_mode = os.environ.get("BL_RBAC_MODE", "strict").strip().lower()
    if rbac_mode not in _RBAC_MODES:
        raise RuntimeError(f"BL_RBAC_MODE doit être dans {sorted(_RBAC_MODES)}.")
    if environment == "prod" and rbac_mode != "strict":
        raise RuntimeError("Le RBAC ne peut pas être désactivé en production.")

    image_backend = os.environ.get("BL_IMAGE_BACKEND", "volume").strip().lower()
    if image_backend not in _IMAGE_BACKENDS:
        raise RuntimeError(f"BL_IMAGE_BACKEND doit être dans {sorted(_IMAGE_BACKENDS)}.")
    volume_path = os.environ.get("BL_VOLUME_PATH", "").strip().rstrip("/")
    if image_backend == "volume" and environment != "local" and not volume_path.startswith("/Volumes/"):
        raise RuntimeError(
            "BL_VOLUME_PATH doit désigner un volume Unity Catalog "
            "(/Volumes/catalogue/schema/volume)."
        )

    max_image_bytes = _int("BL_MAX_IMAGE_BYTES", 4 * 1024 * 1024, 256_000, 20 * 1024 * 1024)
    max_pages = _int("BL_MAX_PAGES", 20, 1, 100)
    max_total_bytes = _int(
        "BL_MAX_TOTAL_BYTES",
        min(50 * 1024 * 1024, max_image_bytes * max_pages),
        max_image_bytes,
        250 * 1024 * 1024,
    )

    return Settings(
        environment=environment,
        pg_schema=schema,
        timezone=os.environ.get("BL_TIMEZONE", os.environ.get("BL_FUSEAU", "Europe/Paris")),
        page_size_default=_int("BL_PAGE_SIZE", 50, 10, 500),
        max_image_bytes=max_image_bytes,
        max_total_bytes=max_total_bytes,
        max_dimension_px=_int("BL_MAX_DIMENSION_PX", 3508, 1024, 10000),
        max_pages=max_pages,
        image_backend=image_backend,
        volume_path=volume_path,
        rbac_mode=rbac_mode,
        bootstrap_admins=_csv("BL_BOOTSTRAP_ADMINS"),
        optimistic_locking=_bool("BL_OPTIMISTIC_LOCKING", True),
        database_pool_min=_int("BL_DB_POOL_MIN", 1, 1, 10),
        database_pool_max=_int("BL_DB_POOL_MAX", 8, 1, 50),
        database_pool_lifetime_s=_int("BL_DB_POOL_LIFETIME_S", 2400, 300, 3300),
        database_connect_timeout_s=_int("BL_DB_CONNECT_TIMEOUT_S", 8, 2, 30),
        notification_max_attempts=_int("BL_NOTIFICATION_MAX_ATTEMPTS", 8, 1, 30),
        notification_batch_size=_int("BL_NOTIFICATION_BATCH_SIZE", 100, 1, 1000),
        llm_endpoint=os.environ.get("BL_LLM_ENDPOINT", "").strip(),
        llm_prompt_version=os.environ.get("BL_LLM_PROMPT_VERSION", "2026-07-01").strip(),
    )


def reset_settings_cache() -> None:
    """Réservé aux tests et aux outils de validation."""
    get_settings.cache_clear()
