"""Tests de l'agrégat KycCase (BE-029)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from flash.domain.identity.kyc import KycTier
from flash.domain.identity.kyc_case import (
    KycCase,
    KycCaseStatus,
    KycDocument,
    KycDocumentKind,
)
from flash.domain.shared.errors import InvalidAccountState, InvalidInput
from flash.domain.shared.identifiers import EntityId

T0 = datetime(2026, 1, 1, tzinfo=UTC)
CASE = EntityId(str(UUID(int=1)))
USER = EntityId(str(UUID(int=2)))
REVIEWER = EntityId(str(UUID(int=3)))


def _doc(kind: KycDocumentKind) -> KycDocument:
    return KycDocument(
        kind=kind,
        storage_key=f"u/c/{kind.value}",
        content_type="image/jpeg",
        byte_size=1024,
        uploaded_at=T0,
    )


def _tier1_docs() -> list[KycDocument]:
    return [_doc(KycDocumentKind.ID_FRONT), _doc(KycDocumentKind.SELFIE)]


def _submit(**kw: object) -> KycCase:
    params: dict[str, object] = {
        "case_id": CASE,
        "user_id": USER,
        "target_tier": KycTier.TIER_1,
        "documents": _tier1_docs(),
        "now": T0,
    }
    params.update(kw)
    return KycCase.submit(**params)  # type: ignore[arg-type]


class TestSubmit:
    def test_submit_is_pending_and_records_event(self) -> None:
        case = _submit()
        assert case.status is KycCaseStatus.PENDING
        assert case.target_tier is KycTier.TIER_1
        assert [e.name for e in case.pull_events()] == ["KycCaseSubmitted"]

    def test_tier_zero_rejected(self) -> None:
        with pytest.raises(InvalidInput, match="supérieur à 0"):
            _submit(target_tier=KycTier.TIER_0)

    def test_missing_required_document_rejected(self) -> None:
        with pytest.raises(InvalidInput, match="Pièces manquantes"):
            _submit(documents=[_doc(KycDocumentKind.ID_FRONT)])

    def test_duplicate_document_kind_rejected(self) -> None:
        with pytest.raises(InvalidInput, match="plusieurs fois"):
            _submit(
                documents=[
                    _doc(KycDocumentKind.ID_FRONT),
                    _doc(KycDocumentKind.SELFIE),
                    _doc(KycDocumentKind.SELFIE),
                ]
            )

    def test_tier2_requires_four_documents(self) -> None:
        with pytest.raises(InvalidInput, match="Pièces manquantes"):
            _submit(target_tier=KycTier.TIER_2, documents=_tier1_docs())
        case = _submit(
            target_tier=KycTier.TIER_2,
            documents=[
                _doc(KycDocumentKind.ID_FRONT),
                _doc(KycDocumentKind.ID_BACK),
                _doc(KycDocumentKind.SELFIE),
                _doc(KycDocumentKind.PROOF_OF_ADDRESS),
            ],
        )
        assert case.status is KycCaseStatus.PENDING

    def test_empty_document_rejected(self) -> None:
        with pytest.raises(InvalidInput, match="vide"):
            KycDocument(
                kind=KycDocumentKind.SELFIE,
                storage_key="k",
                content_type="image/png",
                byte_size=0,
                uploaded_at=T0,
            )

    def test_document_without_storage_key_rejected(self) -> None:
        with pytest.raises(InvalidInput, match="Clé de stockage"):
            KycDocument(
                kind=KycDocumentKind.SELFIE,
                storage_key="",
                content_type="image/png",
                byte_size=10,
                uploaded_at=T0,
            )


class TestReview:
    def test_approve_records_event_carrying_target_tier(self) -> None:
        case = _submit()
        case.pull_events()
        case.approve(reviewer_id=REVIEWER, now=T0)
        assert case.status is KycCaseStatus.APPROVED
        assert case.reviewer_id == REVIEWER
        [event] = case.pull_events()
        assert event.name == "KycCaseApproved"
        assert event.target_tier == 1  # type: ignore[attr-defined]

    def test_reject_requires_reason(self) -> None:
        case = _submit()
        with pytest.raises(InvalidInput, match="motif"):
            case.reject(reviewer_id=REVIEWER, reason="   ", now=T0)

    def test_reject_records_reason(self) -> None:
        case = _submit()
        case.pull_events()
        case.reject(reviewer_id=REVIEWER, reason="Selfie illisible", now=T0)
        assert case.status is KycCaseStatus.REJECTED
        assert case.decision_reason == "Selfie illisible"
        assert [e.name for e in case.pull_events()] == ["KycCaseRejected"]

    def test_cannot_review_twice(self) -> None:
        case = _submit()
        case.approve(reviewer_id=REVIEWER, now=T0)
        with pytest.raises(InvalidAccountState, match="déjà été traité"):
            case.reject(reviewer_id=REVIEWER, reason="trop tard", now=T0)

    def test_withdraw_only_when_pending(self) -> None:
        case = _submit()
        case.pull_events()
        case.withdraw(T0)
        assert case.status is KycCaseStatus.WITHDRAWN
        assert [e.name for e in case.pull_events()] == ["KycCaseWithdrawn"]
        with pytest.raises(InvalidAccountState):
            case.withdraw(T0)

    def test_repr(self) -> None:
        assert "status=PENDING" in repr(_submit())
