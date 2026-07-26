"""Stockage gouverné des pages de BL.

Le backend nominal utilise un volume Unity Catalog via la Files API. Le mode
``database`` reste disponible pour une migration progressive des installations
existantes, mais n'est pas recommandé en production.
"""

from __future__ import annotations

import hashlib
import io
import logging
from dataclasses import dataclass
from functools import lru_cache

from .config import get_settings

logger = logging.getLogger("bl.storage")


@dataclass(frozen=True)
class StoredObject:
    uri: str
    sha256: str
    size_bytes: int
    content_type: str = "image/jpeg"


class VolumeStore:
    def __init__(self, root: str) -> None:
        if not root.startswith("/Volumes/"):
            raise ValueError("Le chemin du volume doit commencer par /Volumes/.")
        self.root = root.rstrip("/")

    @staticmethod
    def _client():
        from databricks.sdk import WorkspaceClient

        return WorkspaceClient()

    def path(self, id_bl: str, index_page: int, id_photo: str) -> str:
        return f"{self.root}/bl/{id_bl}/{index_page:04d}-{id_photo}.jpg"

    def put(self, id_bl: str, index_page: int, id_photo: str, contents: bytes) -> StoredObject:
        uri = self.path(id_bl, index_page, id_photo)
        client = self._client()
        client.files.create_directory(uri.rsplit("/", 1)[0])
        client.files.upload(uri, io.BytesIO(contents), overwrite=False)
        return StoredObject(
            uri=uri,
            sha256=hashlib.sha256(contents).hexdigest(),
            size_bytes=len(contents),
        )

    def get(self, uri: str) -> bytes:
        if not uri.startswith(self.root + "/"):
            raise ValueError("URI de document hors du volume autorisé.")
        response = self._client().files.download(uri)
        with response.contents as stream:
            return stream.read()

    def delete(self, uri: str) -> None:
        if not uri.startswith(self.root + "/"):
            raise ValueError("URI de document hors du volume autorisé.")
        self._client().files.delete(uri)


@lru_cache(maxsize=1)
def volume_store() -> VolumeStore:
    return VolumeStore(get_settings().volume_path)
