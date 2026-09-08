"""Implémentations du port ``DocumentStore`` (pièces justificatives KYC).

``LocalFilesystemDocumentStore`` écrit les octets sous un répertoire racine — suffisant
pour un déploiement mono-VPS et gratuit. Le port permet de brancher un stockage objet
(S3/MinIO) sans toucher au domaine ni aux cas d'usage.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from flash.application.identity.documents import DocumentStore, StoredDocument

_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
}


class LocalFilesystemDocumentStore(DocumentStore):
    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)

    def put(
        self, *, owner_id: str, case_id: str, kind: str, data: bytes, content_type: str
    ) -> StoredDocument:
        digest = hashlib.sha256(data).hexdigest()[:16]
        ext = _EXTENSIONS.get(content_type, ".bin")
        rel = f"{owner_id}/{case_id}/{kind}-{digest}{ext}"
        path = self._root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return StoredDocument(storage_key=rel, content_type=content_type, byte_size=len(data))

    def get(self, storage_key: str) -> bytes:
        path = self._root / storage_key
        try:
            return path.read_bytes()
        except FileNotFoundError as exc:
            raise KeyError(storage_key) from exc


class InMemoryDocumentStore(DocumentStore):
    """Variante sans I/O — utile pour les smoke tests et le développement local."""

    def __init__(self) -> None:
        self._blobs: dict[str, bytes] = {}

    def put(
        self, *, owner_id: str, case_id: str, kind: str, data: bytes, content_type: str
    ) -> StoredDocument:
        digest = hashlib.sha256(data).hexdigest()[:16]
        key = f"{owner_id}/{case_id}/{kind}-{digest}"
        self._blobs[key] = data
        return StoredDocument(storage_key=key, content_type=content_type, byte_size=len(data))

    def get(self, storage_key: str) -> bytes:
        try:
            return self._blobs[storage_key]
        except KeyError:
            raise KeyError(storage_key) from None


__all__ = ["InMemoryDocumentStore", "LocalFilesystemDocumentStore"]
