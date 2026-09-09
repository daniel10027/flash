"""Vérification d'identité par paliers (BE-029).

- ``SubmitKyc`` : l'utilisateur téléverse ses pièces (encodées base64) et ouvre un
  dossier visant un palier supérieur. Idempotent. Les octets partent dans le
  ``DocumentStore`` ; le domaine ne garde qu'une clé de stockage.
- ``WithdrawKyc`` : l'utilisateur retire son dossier tant qu'il est en attente.
- ``ListMyKycCases`` / ``GetKycStatus`` : suivi côté client.
- ``ReviewKyc`` : back-office. ``approve`` relève ``KycTier`` de l'utilisateur (les
  limites étant résolues par ``(pays, palier)`` à chaque opération, elles se
  « rechargent » d'elles-mêmes) ; ``reject`` clôt le dossier avec un motif.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass, field
from typing import Any

from flash.application.idempotency import IdempotencyGuard
from flash.application.identity.documents import DocumentStore
from flash.application.services import AppServices
from flash.application.transaction import execute_in_uow
from flash.application.unit_of_work import WorkUnitOfWork
from flash.application.use_case import Command, UseCase
from flash.domain.identity.kyc import KycTier
from flash.domain.identity.kyc_case import (
    KycCase,
    KycCaseStatus,
    KycDocument,
    KycDocumentKind,
)
from flash.domain.shared.errors import DuplicateOperation, InvalidInput
from flash.domain.shared.identifiers import EntityId, IdempotencyKey

# Types MIME acceptés pour une pièce et taille maximale (5 Mio).
_ALLOWED_CONTENT_TYPES = frozenset({"image/jpeg", "image/png", "image/webp", "application/pdf"})
_MAX_DOCUMENT_BYTES = 5 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class KycDocumentInput:
    kind: str
    content_base64: str
    content_type: str


@dataclass(frozen=True, slots=True)
class KycCaseView:
    case_id: str
    user_id: str
    target_tier: int
    status: str
    document_kinds: list[str]
    submitted_at: str
    decided_at: str | None
    decision_reason: str | None

    @classmethod
    def of(cls, case: KycCase) -> KycCaseView:
        return cls(
            case_id=str(case.id),
            user_id=str(case.user_id),
            target_tier=int(case.target_tier),
            status=case.status.value,
            document_kinds=sorted(d.kind.value for d in case.documents),
            submitted_at=case.submitted_at.isoformat(),
            decided_at=case.decided_at.isoformat() if case.decided_at else None,
            decision_reason=case.decision_reason,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "user_id": self.user_id,
            "target_tier": self.target_tier,
            "status": self.status,
            "document_kinds": self.document_kinds,
            "submitted_at": self.submitted_at,
            "decided_at": self.decided_at,
            "decision_reason": self.decision_reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> KycCaseView:
        return cls(**{k: data[k] for k in cls.__dataclass_fields__})


def _decode_document(raw: KycDocumentInput) -> tuple[KycDocumentKind, bytes, str]:
    try:
        kind = KycDocumentKind(raw.kind.upper())
    except ValueError as exc:
        raise InvalidInput(f"Type de pièce inconnu : {raw.kind!r}.") from exc
    content_type = raw.content_type.lower().strip()
    if content_type not in _ALLOWED_CONTENT_TYPES:
        raise InvalidInput(f"Type de fichier non accepté : {content_type!r}.")
    try:
        data = base64.b64decode(raw.content_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise InvalidInput("Contenu base64 invalide pour une pièce.") from exc
    if not data:
        raise InvalidInput("Pièce vide.")
    if len(data) > _MAX_DOCUMENT_BYTES:
        raise InvalidInput("Pièce trop volumineuse (max 5 Mio).")
    return kind, data, content_type


# ------------------------------------------------------------------- soumettre
@dataclass(frozen=True, slots=True)
class SubmitKycCommand(Command):
    user_id: str
    target_tier: int
    documents: list[KycDocumentInput] = field(default_factory=list)
    idempotency_key: str = ""


class SubmitKyc(UseCase[SubmitKycCommand, KycCaseView]):
    def __init__(self, *, services: AppServices, documents: DocumentStore) -> None:
        self._services = services
        self._documents = documents
        self._guard = IdempotencyGuard(services.idempotency)

    def execute(self, command: SubmitKycCommand) -> KycCaseView:
        try:
            target = KycTier(command.target_tier)
        except ValueError as exc:
            raise InvalidInput("Palier KYC visé invalide.") from exc
        if not command.documents:
            raise InvalidInput("Aucune pièce fournie.")
        try:
            key = IdempotencyKey(command.idempotency_key)
        except ValueError as exc:
            raise InvalidInput(str(exc)) from exc

        decoded = [_decode_document(d) for d in command.documents]
        outcome = self._guard.run(
            key=key,
            subject=command.user_id,
            route="POST /v1/kyc/submissions",
            produce=lambda: self._submit(command.user_id, target, decoded),
            rebuild=KycCaseView.from_dict,
        )
        return outcome.result

    def _submit(
        self,
        user_id: str,
        target: KycTier,
        decoded: list[tuple[KycDocumentKind, bytes, str]],
    ) -> tuple[KycCaseView, dict[str, Any]]:
        now = self._services.clock.now()
        case_id = self._services.ids.new_id()
        stored: list[KycDocument] = []
        for kind, data, content_type in decoded:
            put = self._documents.put(
                owner_id=user_id,
                case_id=str(case_id),
                kind=kind.value,
                data=data,
                content_type=content_type,
            )
            stored.append(
                KycDocument(
                    kind=kind,
                    storage_key=put.storage_key,
                    content_type=put.content_type,
                    byte_size=put.byte_size,
                    uploaded_at=now,
                )
            )
        captured: list[KycCaseView] = []

        def work(uow: WorkUnitOfWork) -> None:
            user = uow.users.get(EntityId(user_id))
            if user is None:  # pragma: no cover - jeton valide => compte existant
                raise InvalidInput("Compte introuvable.")
            if target <= user.kyc_tier:
                raise InvalidInput("Ce palier est déjà atteint.")
            if uow.kyc_cases.get_pending_for_user(user.id) is not None:
                raise DuplicateOperation()
            case = KycCase.submit(
                case_id=case_id,
                user_id=user.id,
                target_tier=target,
                documents=stored,
                now=now,
            )
            uow.kyc_cases.add(case)
            captured.append(KycCaseView.of(case))

        execute_in_uow(self._services.uow, self._services.events, work)
        return captured[0], captured[0].to_dict()


# ------------------------------------------------------------------- retirer
@dataclass(frozen=True, slots=True)
class WithdrawKycCommand(Command):
    user_id: str
    case_id: str


class WithdrawKyc(UseCase[WithdrawKycCommand, None]):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self, command: WithdrawKycCommand) -> None:
        now = self._services.clock.now()

        def work(uow: WorkUnitOfWork) -> None:
            case = uow.kyc_cases.get(EntityId(command.case_id))
            if case is None or str(case.user_id) != command.user_id:
                raise InvalidInput("Dossier KYC introuvable.")
            case.withdraw(now)
            uow.kyc_cases.save(case)

        execute_in_uow(self._services.uow, self._services.events, work)


# ------------------------------------------------------------------- suivi
@dataclass(frozen=True, slots=True)
class ListMyKycCasesCommand(Command):
    user_id: str


class ListMyKycCases(UseCase[ListMyKycCasesCommand, list[KycCaseView]]):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self, command: ListMyKycCasesCommand) -> list[KycCaseView]:
        with self._services.uow() as uow:
            cases = uow.kyc_cases.list_for_user(EntityId(command.user_id))
            return [KycCaseView.of(c) for c in cases]


@dataclass(frozen=True, slots=True)
class KycStatusView:
    kyc_tier: int
    kyc_tier_label: str
    pending_case: KycCaseView | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kyc_tier": self.kyc_tier,
            "kyc_tier_label": self.kyc_tier_label,
            "pending_case": self.pending_case.to_dict() if self.pending_case else None,
        }


@dataclass(frozen=True, slots=True)
class GetKycStatusCommand(Command):
    user_id: str


class GetKycStatus(UseCase[GetKycStatusCommand, KycStatusView]):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self, command: GetKycStatusCommand) -> KycStatusView:
        with self._services.uow() as uow:
            user = uow.users.get(EntityId(command.user_id))
            if user is None:  # pragma: no cover
                raise InvalidInput("Compte introuvable.")
            pending = uow.kyc_cases.get_pending_for_user(user.id)
            return KycStatusView(
                kyc_tier=int(user.kyc_tier),
                kyc_tier_label=user.kyc_tier.label,
                pending_case=KycCaseView.of(pending) if pending else None,
            )


# ------------------------------------------------------------------- back-office
@dataclass(frozen=True, slots=True)
class ReviewKycCommand(Command):
    case_id: str
    reviewer_id: str
    approve: bool
    reason: str = ""


class ReviewKyc(UseCase[ReviewKycCommand, KycCaseView]):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self, command: ReviewKycCommand) -> KycCaseView:
        now = self._services.clock.now()
        reviewer = EntityId(command.reviewer_id)
        captured: list[KycCaseView] = []

        def work(uow: WorkUnitOfWork) -> None:
            case = uow.kyc_cases.get(EntityId(command.case_id))
            if case is None:
                raise InvalidInput("Dossier KYC introuvable.")
            if command.approve:
                case.approve(reviewer_id=reviewer, now=now)
                user = uow.users.get(case.user_id)
                if user is None:  # pragma: no cover - intégrité référentielle
                    raise InvalidInput("Compte du dossier introuvable.")
                user.change_kyc_tier(KycTier(case.target_tier), now)
                uow.users.save(user)
            else:
                case.reject(reviewer_id=reviewer, reason=command.reason, now=now)
            uow.kyc_cases.save(case)
            captured.append(KycCaseView.of(case))

        execute_in_uow(self._services.uow, self._services.events, work)
        return captured[0]


# ------------------------------------------------------------------- back-office : file
@dataclass(frozen=True, slots=True)
class KycDocumentMeta:
    kind: str
    content_type: str
    byte_size: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "content_type": self.content_type,
            "byte_size": self.byte_size,
        }


@dataclass(frozen=True, slots=True)
class KycCaseDetailView:
    case: KycCaseView
    documents: list[KycDocumentMeta]

    def to_dict(self) -> dict[str, Any]:
        return {**self.case.to_dict(), "documents": [d.to_dict() for d in self.documents]}

    @classmethod
    def of(cls, case: KycCase) -> KycCaseDetailView:
        return cls(
            case=KycCaseView.of(case),
            documents=[
                KycDocumentMeta(
                    kind=d.kind.value,
                    content_type=d.content_type,
                    byte_size=d.byte_size,
                )
                for d in case.documents
            ],
        )


@dataclass(frozen=True, slots=True)
class ListKycQueueCommand(Command):
    status: str = "PENDING"
    limit: int = 200


class ListKycQueue(UseCase[ListKycQueueCommand, list[KycCaseView]]):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self, command: ListKycQueueCommand) -> list[KycCaseView]:
        try:
            status = KycCaseStatus(command.status.upper())
        except ValueError as exc:
            raise InvalidInput(f"Statut KYC inconnu : {command.status!r}.") from exc
        with self._services.uow() as uow:
            cases = uow.kyc_cases.list_by_status(status, limit=max(1, command.limit))
            return [KycCaseView.of(c) for c in cases]


@dataclass(frozen=True, slots=True)
class GetKycCaseCommand(Command):
    case_id: str


class GetKycCase(UseCase[GetKycCaseCommand, KycCaseDetailView]):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self, command: GetKycCaseCommand) -> KycCaseDetailView:
        with self._services.uow() as uow:
            case = uow.kyc_cases.get(EntityId(command.case_id))
            if case is None:
                raise InvalidInput("Dossier KYC introuvable.")
            return KycCaseDetailView.of(case)


@dataclass(frozen=True, slots=True)
class GetKycDocumentCommand(Command):
    case_id: str
    kind: str


@dataclass(frozen=True, slots=True)
class KycDocumentBytes:
    data: bytes
    content_type: str


class GetKycDocument(UseCase[GetKycDocumentCommand, KycDocumentBytes]):
    def __init__(self, *, services: AppServices, documents: DocumentStore) -> None:
        self._services = services
        self._documents = documents

    def execute(self, command: GetKycDocumentCommand) -> KycDocumentBytes:
        try:
            kind = KycDocumentKind(command.kind.upper())
        except ValueError as exc:
            raise InvalidInput(f"Type de pièce inconnu : {command.kind!r}.") from exc
        with self._services.uow() as uow:
            case = uow.kyc_cases.get(EntityId(command.case_id))
            if case is None:
                raise InvalidInput("Dossier KYC introuvable.")
            doc = next((d for d in case.documents if d.kind is kind), None)
            if doc is None:
                raise InvalidInput("Pièce absente de ce dossier.")
        try:
            data = self._documents.get(doc.storage_key)
        except KeyError as exc:
            raise InvalidInput("Pièce introuvable dans le stockage.") from exc
        return KycDocumentBytes(data=data, content_type=doc.content_type)


__all__ = [
    "GetKycCase",
    "GetKycCaseCommand",
    "GetKycDocument",
    "GetKycDocumentCommand",
    "GetKycStatus",
    "GetKycStatusCommand",
    "KycCaseDetailView",
    "KycCaseView",
    "KycDocumentBytes",
    "KycDocumentInput",
    "KycStatusView",
    "ListKycQueue",
    "ListKycQueueCommand",
    "ListMyKycCases",
    "ListMyKycCasesCommand",
    "ReviewKyc",
    "ReviewKycCommand",
    "SubmitKyc",
    "SubmitKycCommand",
    "WithdrawKyc",
    "WithdrawKycCommand",
]
