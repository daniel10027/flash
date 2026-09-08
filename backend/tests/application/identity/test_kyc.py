"""Tests des cas d'usage KYC : soumission, retrait, suivi, revue back-office (BE-029)."""

from __future__ import annotations

import base64
from uuid import UUID

import pytest

from flash.application.identity.kyc import (
    GetKycStatus,
    GetKycStatusCommand,
    KycDocumentInput,
    ListMyKycCases,
    ListMyKycCasesCommand,
    ReviewKyc,
    ReviewKycCommand,
    SubmitKyc,
    SubmitKycCommand,
    WithdrawKyc,
    WithdrawKycCommand,
)
from flash.application.services import AppServices
from flash.domain.identity.kyc import KycTier
from flash.domain.identity.pin import Pin
from flash.domain.identity.user import User
from flash.domain.shared.errors import DuplicateOperation, InvalidAccountState, InvalidInput
from flash.domain.shared.identifiers import CountryCode, EntityId, Msisdn
from flash.infrastructure.documents import InMemoryDocumentStore
from tests.support.fakes import (
    FakePinHasher,
    FixedClock,
    InMemoryIdempotencyStore,
    RecordingEventPublisher,
    SeqIdGenerator,
)
from tests.support.repositories import InMemoryUnitOfWork

CI = CountryCode("CI")
USER_ID = str(UUID(int=1))
REVIEWER_ID = str(UUID(int=99))
_PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 64).decode()


@pytest.fixture
def uow() -> InMemoryUnitOfWork:
    return InMemoryUnitOfWork()


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock()


@pytest.fixture
def documents() -> InMemoryDocumentStore:
    return InMemoryDocumentStore()


@pytest.fixture
def services(uow: InMemoryUnitOfWork, clock: FixedClock) -> AppServices:
    return AppServices(
        uow=lambda: uow,
        clock=clock,
        ids=SeqIdGenerator(),
        events=RecordingEventPublisher(),
        idempotency=InMemoryIdempotencyStore(),
    )


def _user(uow: InMemoryUnitOfWork) -> User:
    user = User.register(
        user_id=EntityId(USER_ID),
        country=CI,
        msisdn=Msisdn("+2250700000001"),
        pin_hash=FakePinHasher().hash(Pin("1397")),
        now=FixedClock().now(),
    )
    user.activate(FixedClock().now())
    user.pull_events()
    uow.users.add(user)
    return user


def _docs(*kinds: str) -> list[KycDocumentInput]:
    return [KycDocumentInput(kind=k, content_base64=_PNG, content_type="image/png") for k in kinds]


def _submit(services: AppServices, *, key: str = "kyc-key-0001", tier: int = 1) -> str:
    view = SubmitKyc(services=services, documents=InMemoryDocumentStore()).execute(
        SubmitKycCommand(
            user_id=USER_ID,
            target_tier=tier,
            documents=_docs("ID_FRONT", "SELFIE"),
            idempotency_key=key,
        )
    )
    return view.case_id


class TestSubmitKyc:
    def test_submit_stores_documents_and_opens_pending_case(
        self, services: AppServices, uow: InMemoryUnitOfWork, documents: InMemoryDocumentStore
    ) -> None:
        _user(uow)
        view = SubmitKyc(services=services, documents=documents).execute(
            SubmitKycCommand(
                user_id=USER_ID,
                target_tier=1,
                documents=_docs("ID_FRONT", "SELFIE"),
                idempotency_key="kyc-key-0001",
            )
        )
        assert view.status == "PENDING"
        assert view.document_kinds == ["ID_FRONT", "SELFIE"]
        pending = uow.kyc_cases.get_pending_for_user(EntityId(USER_ID))
        assert pending is not None
        assert all(d.storage_key for d in pending.documents)

    def test_replay_same_key_returns_same_case(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow)
        first = _submit(services, key="kyc-key-replay")
        second = _submit(services, key="kyc-key-replay")
        assert first == second

    def test_second_pending_case_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow)
        _submit(services, key="kyc-key-a")
        with pytest.raises(DuplicateOperation):
            _submit(services, key="kyc-key-b")

    def test_invalid_base64_rejected(self, services: AppServices, uow: InMemoryUnitOfWork) -> None:
        _user(uow)
        with pytest.raises(InvalidInput, match="base64"):
            SubmitKyc(services=services, documents=InMemoryDocumentStore()).execute(
                SubmitKycCommand(
                    user_id=USER_ID,
                    target_tier=1,
                    documents=[
                        KycDocumentInput(
                            kind="ID_FRONT", content_base64="not base64!!", content_type="image/png"
                        ),
                        *_docs("SELFIE"),
                    ],
                    idempotency_key="kyc-key-bad64",
                )
            )

    def test_unsupported_content_type_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow)
        with pytest.raises(InvalidInput, match="non accepté"):
            SubmitKyc(services=services, documents=InMemoryDocumentStore()).execute(
                SubmitKycCommand(
                    user_id=USER_ID,
                    target_tier=1,
                    documents=[
                        KycDocumentInput(
                            kind="ID_FRONT", content_base64=_PNG, content_type="text/plain"
                        ),
                        *_docs("SELFIE"),
                    ],
                    idempotency_key="kyc-key-badtype",
                )
            )

    def test_target_tier_not_above_current_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork, clock: FixedClock
    ) -> None:
        user = _user(uow)
        user.change_kyc_tier(KycTier.TIER_1, clock.now())
        user.pull_events()
        with pytest.raises(InvalidInput, match="déjà atteint"):
            _submit(services, key="kyc-key-same-tier")

    def test_no_documents_rejected(self, services: AppServices, uow: InMemoryUnitOfWork) -> None:
        _user(uow)
        with pytest.raises(InvalidInput, match="Aucune pièce"):
            SubmitKyc(services=services, documents=InMemoryDocumentStore()).execute(
                SubmitKycCommand(
                    user_id=USER_ID, target_tier=1, documents=[], idempotency_key="kyc-key-nodoc"
                )
            )

    def test_bad_target_tier_value_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow)
        with pytest.raises(InvalidInput, match="Palier KYC visé"):
            SubmitKyc(services=services, documents=InMemoryDocumentStore()).execute(
                SubmitKycCommand(
                    user_id=USER_ID,
                    target_tier=7,
                    documents=_docs("ID_FRONT", "SELFIE"),
                    idempotency_key="kyc-key-badtier",
                )
            )

    def test_unknown_document_kind_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow)
        with pytest.raises(InvalidInput, match="Type de pièce inconnu"):
            SubmitKyc(services=services, documents=InMemoryDocumentStore()).execute(
                SubmitKycCommand(
                    user_id=USER_ID,
                    target_tier=1,
                    documents=[
                        KycDocumentInput(
                            kind="PASSPORT", content_base64=_PNG, content_type="image/png"
                        )
                    ],
                    idempotency_key="kyc-key-badkind",
                )
            )

    def test_empty_decoded_document_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow)
        with pytest.raises(InvalidInput, match="vide"):
            SubmitKyc(services=services, documents=InMemoryDocumentStore()).execute(
                SubmitKycCommand(
                    user_id=USER_ID,
                    target_tier=1,
                    documents=[
                        KycDocumentInput(
                            kind="ID_FRONT", content_base64="", content_type="image/png"
                        ),
                        *_docs("SELFIE"),
                    ],
                    idempotency_key="kyc-key-emptydoc",
                )
            )

    def test_oversized_document_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow)
        big = base64.b64encode(b"0" * (5 * 1024 * 1024 + 1)).decode()
        with pytest.raises(InvalidInput, match="trop volumineuse"):
            SubmitKyc(services=services, documents=InMemoryDocumentStore()).execute(
                SubmitKycCommand(
                    user_id=USER_ID,
                    target_tier=1,
                    documents=[
                        KycDocumentInput(
                            kind="ID_FRONT", content_base64=big, content_type="image/png"
                        ),
                        *_docs("SELFIE"),
                    ],
                    idempotency_key="kyc-key-toobig",
                )
            )

    def test_short_idempotency_key_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow)
        with pytest.raises(InvalidInput):
            _submit(services, key="x")


class TestWithdrawAndStatus:
    def test_status_reports_tier_and_pending_case(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow)
        case_id = _submit(services)
        status = GetKycStatus(services=services).execute(GetKycStatusCommand(user_id=USER_ID))
        assert status.kyc_tier == 0
        assert status.pending_case is not None
        assert status.pending_case.case_id == case_id

    def test_withdraw_clears_pending_case(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow)
        case_id = _submit(services)
        WithdrawKyc(services=services).execute(WithdrawKycCommand(user_id=USER_ID, case_id=case_id))
        assert uow.kyc_cases.get_pending_for_user(EntityId(USER_ID)) is None
        listed = ListMyKycCases(services=services).execute(ListMyKycCasesCommand(user_id=USER_ID))
        assert [c.status for c in listed] == ["WITHDRAWN"]

    def test_withdraw_unknown_case_rejected(self, services: AppServices) -> None:
        with pytest.raises(InvalidInput, match="introuvable"):
            WithdrawKyc(services=services).execute(
                WithdrawKycCommand(user_id=USER_ID, case_id=str(UUID(int=555)))
            )

    def test_withdraw_foreign_case_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow)
        case_id = _submit(services)
        with pytest.raises(InvalidInput, match="introuvable"):
            WithdrawKyc(services=services).execute(
                WithdrawKycCommand(user_id=str(UUID(int=2)), case_id=case_id)
            )


class TestReviewKyc:
    def test_approve_bumps_user_tier(self, services: AppServices, uow: InMemoryUnitOfWork) -> None:
        _user(uow)
        case_id = _submit(services)
        view = ReviewKyc(services=services).execute(
            ReviewKycCommand(case_id=case_id, reviewer_id=REVIEWER_ID, approve=True)
        )
        assert view.status == "APPROVED"
        user = uow.users.get(EntityId(USER_ID))
        assert user is not None
        assert user.kyc_tier is KycTier.TIER_1

    def test_reject_keeps_tier_and_stores_reason(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow)
        case_id = _submit(services)
        view = ReviewKyc(services=services).execute(
            ReviewKycCommand(
                case_id=case_id, reviewer_id=REVIEWER_ID, approve=False, reason="Selfie flou"
            )
        )
        assert view.status == "REJECTED"
        assert view.decision_reason == "Selfie flou"
        user = uow.users.get(EntityId(USER_ID))
        assert user is not None and user.kyc_tier is KycTier.TIER_0

    def test_reject_without_reason_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow)
        case_id = _submit(services)
        with pytest.raises(InvalidInput, match="motif"):
            ReviewKyc(services=services).execute(
                ReviewKycCommand(case_id=case_id, reviewer_id=REVIEWER_ID, approve=False)
            )

    def test_review_unknown_case_rejected(self, services: AppServices) -> None:
        with pytest.raises(InvalidInput, match="introuvable"):
            ReviewKyc(services=services).execute(
                ReviewKycCommand(case_id=str(UUID(int=777)), reviewer_id=REVIEWER_ID, approve=True)
            )

    def test_review_twice_rejected(self, services: AppServices, uow: InMemoryUnitOfWork) -> None:
        _user(uow)
        case_id = _submit(services)
        ReviewKyc(services=services).execute(
            ReviewKycCommand(case_id=case_id, reviewer_id=REVIEWER_ID, approve=True)
        )
        with pytest.raises(InvalidAccountState):
            ReviewKyc(services=services).execute(
                ReviewKycCommand(case_id=case_id, reviewer_id=REVIEWER_ID, approve=True)
            )
