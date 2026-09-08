"""Port ``DocumentStore`` — stockage des pièces justificatives KYC.

Le domaine ne connaît que la ``storage_key`` opaque renvoyée par ``put``. L'implémentation
(système de fichiers local, S3, …) est branchée par le conteneur d'injection.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class StoredDocument:
    storage_key: str
    content_type: str
    byte_size: int


@runtime_checkable
class DocumentStore(Protocol):
    def put(
        self, *, owner_id: str, case_id: str, kind: str, data: bytes, content_type: str
    ) -> StoredDocument:
        """Persiste les octets d'une pièce et renvoie sa clé de stockage."""
        ...

    def get(self, storage_key: str) -> bytes:
        """Relit les octets d'une pièce (back-office). Lève ``KeyError`` si absente."""
        ...


__all__ = ["DocumentStore", "StoredDocument"]
