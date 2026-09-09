"""Tests des compléments back-office KYC : file des dossiers, détail avec pièces,
téléchargement des octets d'une pièce (``ListKycQueue`` / ``GetKycCase`` /
``GetKycDocument``)."""

from __future__ import annotations

import base64
from uuid import UUID

import pytest

from flash.application.identity.kyc import (
    GetKycCase,
    GetKycCaseCommand,
    GetKycDocument,
    GetKycDocumentCommand,
    KycDocumentInput,
    ListKycQueue,
    ListKycQueueCommand,
    SubmitKyc,
    SubmitKycCommand,
    WithdrawKyc,
    WithdrawKycCommand,
)
from flash.application.services import AppServices
from flash.domain.identity.pin import Pin
from flash.domain.identity.user import User
from flash.domain.shared.errors import InvalidInput
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
_PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 64).decode()


@pytest.fixture
def uow() -> InMemoryUnitOfWork:
    return InMemoryUnitOfWork()


@pytest.fixture
def documents() -> InMemoryDocumentStore:
    return InMemoryDocumentStore()


@pytest.fixture
def services(uow: InMemoryUnitOfWork) -> AppServices:
    return AppServices(
        uow=lambda: uow,
        clock=FixedClock(),
        ids=SeqIdGenerator(),
        events=RecordingEventPublisher(),
        idempotency=InMemoryIdempotencyStore(),
    )


def _user(uow: InMemoryUnitOfWork, *, n: int) -> str:
    uid = str(UUID(int=n))
    user = User.register(
        user_id=EntityId(uid),
        country=CI,
        msisdn=Msisdn(f"+22507000000{n:02d}"),
        pin_hash=FakePinHasher().hash(Pin("1397")),
        now=FixedClock().now(),
    )
    user.activate(FixedClock().now())
    user.pull_events()
    uow.users.add(user)
    return uid


def _submit(
    services: AppServices,
    documents: InMemoryDocumentStore,
    *,
    user_id: str,
    key: str,
    kinds: tuple[str, ...] = ("ID_FRONT", "SELFIE"),
) -> str:
    view = SubmitKyc(services=services, documents=documents).execute(
        SubmitKycCommand(
            user_id=user_id,
            target_tier=1,
            documents=[
                KycDocumentInput(kind=k, content_base64=_PNG, content_type="image/png")
                for k in kinds
            ],
            idempotency_key=key,
        )
    )
    return view.case_id


class TestListKycQueue:
    def test_lists_pending_cases_oldest_first(
        self, services: AppServices, uow: InMemoryUnitOfWork, documents: InMemoryDocumentStore
    ) -> None:
        u1 = _user(uow, n=1)
        u2 = _user(uow, n=2)
        c1 = _submit(services, documents, user_id=u1, key="kyc-key-0001")
        c2 = _submit(services, documents, user_id=u2, key="kyc-key-0002")

        views = ListKycQueue(services=services).execute(ListKycQueueCommand())

        assert [v.case_id for v in views] == [c1, c2]
        assert all(v.status == "PENDING" for v in views)

    def test_withdrawn_case_not_in_pending_queue(
        self, services: AppServices, uow: InMemoryUnitOfWork, documents: InMemoryDocumentStore
    ) -> None:
        u1 = _user(uow, n=1)
        c1 = _submit(services, documents, user_id=u1, key="kyc-key-0001")
        WithdrawKyc(services=services).execute(WithdrawKycCommand(user_id=u1, case_id=c1))

        assert ListKycQueue(services=services).execute(ListKycQueueCommand()) == []
        withdrawn = ListKycQueue(services=services).execute(
            ListKycQueueCommand(status="withdrawn")
        )
        assert [v.case_id for v in withdrawn] == [c1]

    def test_limit_is_honoured(
        self, services: AppServices, uow: InMemoryUnitOfWork, documents: InMemoryDocumentStore
    ) -> None:
        for i in (1, 2, 3):
            uid = _user(uow, n=i)
            _submit(services, documents, user_id=uid, key=f"kyc-key-{i:04d}")
        views = ListKycQueue(services=services).execute(ListKycQueueCommand(limit=2))
        assert len(views) == 2

    def test_unknown_status_is_invalid_input(self, services: AppServices) -> None:
        with pytest.raises(InvalidInput):
            ListKycQueue(services=services).execute(ListKycQueueCommand(status="BOGUS"))


class TestGetKycCase:
    def test_returns_case_with_document_metadata(
        self, services: AppServices, uow: InMemoryUnitOfWork, documents: InMemoryDocumentStore
    ) -> None:
        u1 = _user(uow, n=1)
        case_id = _submit(services, documents, user_id=u1, key="kyc-key-0001")

        detail = GetKycCase(services=services).execute(GetKycCaseCommand(case_id=case_id))
        payload = detail.to_dict()

        assert payload["case_id"] == case_id
        kinds = {d["kind"] for d in payload["documents"]}
        assert kinds == {"ID_FRONT", "SELFIE"}
        assert all(d["byte_size"] > 0 for d in payload["documents"])

    def test_unknown_case_is_invalid_input(self, services: AppServices) -> None:
        with pytest.raises(InvalidInput):
            GetKycCase(services=services).execute(
                GetKycCaseCommand(case_id=str(UUID(int=123)))
            )


class TestGetKycDocument:
    def test_returns_stored_bytes_and_content_type(
        self, services: AppServices, uow: InMemoryUnitOfWork, documents: InMemoryDocumentStore
    ) -> None:
        u1 = _user(uow, n=1)
        case_id = _submit(services, documents, user_id=u1, key="kyc-key-0001")

        doc = GetKycDocument(services=services, documents=documents).execute(
            GetKycDocumentCommand(case_id=case_id, kind="ID_FRONT")
        )

        assert doc.content_type == "image/png"
        assert doc.data == base64.b64decode(_PNG)

    def test_unknown_kind_is_invalid_input(
        self, services: AppServices, uow: InMemoryUnitOfWork, documents: InMemoryDocumentStore
    ) -> None:
        u1 = _user(uow, n=1)
        case_id = _submit(services, documents, user_id=u1, key="kyc-key-0001")
        with pytest.raises(InvalidInput):
            GetKycDocument(services=services, documents=documents).execute(
                GetKycDocumentCommand(case_id=case_id, kind="NOPE")
            )

    def test_kind_absent_from_case_is_invalid_input(
        self, services: AppServices, uow: InMemoryUnitOfWork, documents: InMemoryDocumentStore
    ) -> None:
        u1 = _user(uow, n=1)
        case_id = _submit(
            services, documents, user_id=u1, key="kyc-key-0001", kinds=("ID_FRONT", "SELFIE")
        )
        with pytest.raises(InvalidInput):
            GetKycDocument(services=services, documents=documents).execute(
                GetKycDocumentCommand(case_id=case_id, kind="ID_BACK")
            )

    def test_missing_bytes_in_store_is_invalid_input(
        self, services: AppServices, uow: InMemoryUnitOfWork, documents: InMemoryDocumentStore
    ) -> None:
        u1 = _user(uow, n=1)
        case_id = _submit(services, documents, user_id=u1, key="kyc-key-0001")
        with pytest.raises(InvalidInput):
            GetKycDocument(services=services, documents=InMemoryDocumentStore()).execute(
                GetKycDocumentCommand(case_id=case_id, kind="ID_FRONT")
            )

    def test_unknown_case_is_invalid_input(
        self, services: AppServices, documents: InMemoryDocumentStore
    ) -> None:
        with pytest.raises(InvalidInput):
            GetKycDocument(services=services, documents=documents).execute(
                GetKycDocumentCommand(case_id=str(UUID(int=123)), kind="ID_FRONT")
            )
