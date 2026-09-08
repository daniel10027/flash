"""Agrégat ``KycCase`` — dossier de vérification d'identité soumis par un utilisateur.

Un utilisateur soumet un dossier visant un palier (``KycTier``) supérieur, accompagné de
pièces justificatives (recto/verso d'une pièce d'identité, selfie, justificatif de
domicile). Le back-office **approuve** (le palier de l'utilisateur est relevé) ou
**rejette** (avec motif). L'utilisateur peut retirer un dossier tant qu'il est en attente.

Les octets des pièces ne transitent jamais par le domaine : seule une **clé de stockage**
(``storage_key``) opaque, produite par le port ``DocumentStore`` de la couche
application, est conservée.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from flash.domain.identity.events import (
    KycCaseApproved,
    KycCaseRejected,
    KycCaseSubmitted,
    KycCaseWithdrawn,
)
from flash.domain.identity.kyc import KycTier
from flash.domain.shared.errors import InvalidAccountState, InvalidInput
from flash.domain.shared.events import EventRecorder
from flash.domain.shared.identifiers import EntityId


class KycDocumentKind(StrEnum):
    ID_FRONT = "ID_FRONT"
    ID_BACK = "ID_BACK"
    SELFIE = "SELFIE"
    PROOF_OF_ADDRESS = "PROOF_OF_ADDRESS"


class KycCaseStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"


# Pièces exigées par palier visé.
_REQUIRED_DOCUMENTS: dict[KycTier, tuple[KycDocumentKind, ...]] = {
    KycTier.TIER_1: (KycDocumentKind.ID_FRONT, KycDocumentKind.SELFIE),
    KycTier.TIER_2: (
        KycDocumentKind.ID_FRONT,
        KycDocumentKind.ID_BACK,
        KycDocumentKind.SELFIE,
        KycDocumentKind.PROOF_OF_ADDRESS,
    ),
}


@dataclass(frozen=True, slots=True)
class KycDocument:
    kind: KycDocumentKind
    storage_key: str
    content_type: str
    byte_size: int
    uploaded_at: datetime

    def __post_init__(self) -> None:
        if not self.storage_key:
            raise InvalidInput("Clé de stockage de pièce manquante.")
        if self.byte_size <= 0:
            raise InvalidInput("Pièce vide.")


class KycCase(EventRecorder):
    def __init__(
        self,
        *,
        id: EntityId,
        user_id: EntityId,
        target_tier: KycTier,
        status: KycCaseStatus,
        documents: Iterable[KycDocument],
        submitted_at: datetime,
        decided_at: datetime | None = None,
        reviewer_id: EntityId | None = None,
        decision_reason: str | None = None,
    ) -> None:
        super().__init__()
        self.id = id
        self.user_id = user_id
        self.target_tier = target_tier
        self.status = status
        self.documents: tuple[KycDocument, ...] = tuple(documents)
        self.submitted_at = submitted_at
        self.decided_at = decided_at
        self.reviewer_id = reviewer_id
        self.decision_reason = decision_reason

    @classmethod
    def submit(
        cls,
        *,
        case_id: EntityId,
        user_id: EntityId,
        target_tier: KycTier,
        documents: Sequence[KycDocument],
        now: datetime,
    ) -> KycCase:
        if target_tier <= KycTier.TIER_0:
            raise InvalidInput("Le palier visé doit être supérieur à 0.")
        provided = [d.kind for d in documents]
        if len(provided) != len(set(provided)):
            raise InvalidInput("Une même pièce a été fournie plusieurs fois.")
        missing = [k.value for k in _REQUIRED_DOCUMENTS[target_tier] if k not in provided]
        if missing:
            raise InvalidInput(f"Pièces manquantes pour ce palier : {', '.join(missing)}.")
        case = cls(
            id=case_id,
            user_id=user_id,
            target_tier=target_tier,
            status=KycCaseStatus.PENDING,
            documents=documents,
            submitted_at=now,
        )
        case.record_event(
            KycCaseSubmitted(
                occurred_at=now,
                aggregate_id=str(case_id),
                user_id=str(user_id),
                target_tier=int(target_tier),
                document_kinds=sorted(k.value for k in provided),
            )
        )
        return case

    def _ensure_pending(self) -> None:
        if self.status is not KycCaseStatus.PENDING:
            raise InvalidAccountState("Ce dossier KYC a déjà été traité.", status=self.status.value)

    def approve(self, *, reviewer_id: EntityId, now: datetime) -> None:
        self._ensure_pending()
        self.status = KycCaseStatus.APPROVED
        self.decided_at = now
        self.reviewer_id = reviewer_id
        self.record_event(
            KycCaseApproved(
                occurred_at=now,
                aggregate_id=str(self.id),
                user_id=str(self.user_id),
                target_tier=int(self.target_tier),
                reviewer_id=str(reviewer_id),
            )
        )

    def reject(self, *, reviewer_id: EntityId, reason: str, now: datetime) -> None:
        self._ensure_pending()
        cleaned = reason.strip()
        if not cleaned:
            raise InvalidInput("Un motif de rejet est requis.")
        self.status = KycCaseStatus.REJECTED
        self.decided_at = now
        self.reviewer_id = reviewer_id
        self.decision_reason = cleaned
        self.record_event(
            KycCaseRejected(
                occurred_at=now,
                aggregate_id=str(self.id),
                user_id=str(self.user_id),
                reviewer_id=str(reviewer_id),
                reason=cleaned,
            )
        )

    def withdraw(self, now: datetime) -> None:
        self._ensure_pending()
        self.status = KycCaseStatus.WITHDRAWN
        self.decided_at = now
        self.record_event(
            KycCaseWithdrawn(occurred_at=now, aggregate_id=str(self.id), user_id=str(self.user_id))
        )

    def __repr__(self) -> str:
        return (
            f"KycCase(id={self.id!s}, user={self.user_id!s}, "
            f"tier={int(self.target_tier)}, status={self.status.value})"
        )


__all__ = [
    "KycCase",
    "KycCaseStatus",
    "KycDocument",
    "KycDocumentKind",
]
