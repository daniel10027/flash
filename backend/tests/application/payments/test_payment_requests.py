"""Tests des cas d'usage des demandes de paiement (BE-032)."""

from __future__ import annotations

from uuid import UUID

import pytest

from flash.application.payments.requests import (
    AcceptPaymentRequest,
    AcceptPaymentRequestCommand,
    CancelPaymentRequest,
    CancelPaymentRequestCommand,
    CreatePaymentRequest,
    CreatePaymentRequestCommand,
    DeclinePaymentRequest,
    DeclinePaymentRequestCommand,
    ListPaymentRequests,
    ListPaymentRequestsCommand,
)
from flash.application.services import AppServices
from flash.application.transfers.send_p2p import SendP2PTransfer
from flash.domain.identity.pin import Pin
from flash.domain.identity.user import User
from flash.domain.limits.limits import KycPolicy, LimitPolicy
from flash.domain.pricing.pricing import PricingService
from flash.domain.shared.errors import (
    InsufficientFunds,
    InvalidAccountState,
    InvalidInput,
    RecipientNotFound,
    SelfTransfer,
)
from flash.domain.shared.identifiers import CountryCode, EntityId, Msisdn
from flash.domain.shared.money import XOF, Money
from flash.domain.wallet.wallet import Wallet
from flash.infrastructure.limits import NullLimitCounter, build_limit_repository
from flash.infrastructure.pricing import build_pricing_repository
from tests.support.fakes import (
    FakePinHasher,
    FixedClock,
    InMemoryIdempotencyStore,
    RecordingEventPublisher,
    SeqIdGenerator,
)
from tests.support.repositories import InMemoryUnitOfWork

CI = CountryCode("CI")
REQUESTER_MSISDN = "+2250700000001"
PAYER_MSISDN = "+2250700000002"


@pytest.fixture
def uow() -> InMemoryUnitOfWork:
    return InMemoryUnitOfWork()


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock()


@pytest.fixture
def services(uow: InMemoryUnitOfWork, clock: FixedClock) -> AppServices:
    return AppServices(
        uow=lambda: uow,
        clock=clock,
        ids=SeqIdGenerator(),
        events=RecordingEventPublisher(),
        idempotency=InMemoryIdempotencyStore(),
    )


@pytest.fixture
def transfers(services: AppServices) -> SendP2PTransfer:
    return SendP2PTransfer(
        services=services,
        pricing=PricingService(build_pricing_repository()),
        limits=LimitPolicy(build_limit_repository(), NullLimitCounter()),
        kyc=KycPolicy(),
    )


def _user(uow: InMemoryUnitOfWork, *, n: int, msisdn: str, balance: int = 0) -> User:
    user = User.register(
        user_id=EntityId(str(UUID(int=n))),
        country=CI,
        msisdn=Msisdn(msisdn),
        pin_hash=FakePinHasher().hash(Pin("1397")),
        now=FixedClock().now(),
    )
    user.activate(FixedClock().now())
    user.pull_events()
    uow.users.add(user)
    wallet = Wallet.open(
        wallet_id=EntityId(str(UUID(int=100 + n))),
        user_id=user.id,
        currency=XOF,
        now=FixedClock().now(),
    )
    if balance:
        wallet.credit(Money(balance, XOF), FixedClock().now())
    wallet.pull_events()
    uow.wallets.add(wallet)
    return user


REQUESTER_ID = str(UUID(int=1))
PAYER_ID = str(UUID(int=2))


def _create(services: AppServices, *, key: str = "prq-key-0001", amount: int = 15_000) -> str:
    view = CreatePaymentRequest(services=services).execute(
        CreatePaymentRequestCommand(
            requester_user_id=REQUESTER_ID,
            payer_phone_number=PAYER_MSISDN,
            amount_minor=amount,
            idempotency_key=key,
            note="Part de taxi",
        )
    )
    return view.request_id


class TestCreate:
    def test_create_opens_pending_request(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow, n=1, msisdn=REQUESTER_MSISDN)
        _user(uow, n=2, msisdn=PAYER_MSISDN)
        request_id = _create(services)
        stored = uow.payment_requests.get(EntityId(request_id))
        assert stored is not None
        assert stored.status.value == "PENDING"
        assert stored.amount == Money(15_000, XOF)

    def test_create_unknown_payer_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow, n=1, msisdn=REQUESTER_MSISDN)
        with pytest.raises(RecipientNotFound):
            _create(services, key="prq-key-nopayer")

    def test_create_self_request_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow, n=1, msisdn=REQUESTER_MSISDN)
        with pytest.raises(SelfTransfer):
            CreatePaymentRequest(services=services).execute(
                CreatePaymentRequestCommand(
                    requester_user_id=REQUESTER_ID,
                    payer_phone_number=REQUESTER_MSISDN,
                    amount_minor=1_000,
                    idempotency_key="prq-key-self",
                )
            )

    def test_create_non_positive_amount_rejected(self, services: AppServices) -> None:
        with pytest.raises(InvalidInput, match="strictement positif"):
            CreatePaymentRequest(services=services).execute(
                CreatePaymentRequestCommand(
                    requester_user_id=REQUESTER_ID,
                    payer_phone_number=PAYER_MSISDN,
                    amount_minor=0,
                    idempotency_key="prq-key-zero",
                )
            )

    def test_create_short_key_rejected(self, services: AppServices) -> None:
        with pytest.raises(InvalidInput):
            _create(services, key="x")

    def test_create_is_idempotent(self, services: AppServices, uow: InMemoryUnitOfWork) -> None:
        _user(uow, n=1, msisdn=REQUESTER_MSISDN)
        _user(uow, n=2, msisdn=PAYER_MSISDN)
        assert _create(services, key="prq-key-rep") == _create(services, key="prq-key-rep")


class TestAccept:
    def test_accept_triggers_transfer_and_marks_accepted(
        self, services: AppServices, uow: InMemoryUnitOfWork, transfers: SendP2PTransfer
    ) -> None:
        _user(uow, n=1, msisdn=REQUESTER_MSISDN)
        _user(uow, n=2, msisdn=PAYER_MSISDN, balance=100_000)
        request_id = _create(services)

        result = AcceptPaymentRequest(services=services, transfers=transfers).execute(
            AcceptPaymentRequestCommand(payer_user_id=PAYER_ID, request_id=request_id)
        )
        assert result.transfer.amount_minor == 15_000
        assert result.request.status == "ACCEPTED"
        assert result.request.resulting_transfer_id == result.transfer.transfer_id

        payer_wallet = uow.wallets.get_for_user(EntityId(PAYER_ID), XOF)
        requester_wallet = uow.wallets.get_for_user(EntityId(REQUESTER_ID), XOF)
        assert payer_wallet is not None and requester_wallet is not None
        # 15 000 + frais 0,8 % (120) débités au payeur ; 15 000 crédités au demandeur
        assert payer_wallet.available == Money(100_000 - 15_120, XOF)
        assert requester_wallet.available == Money(15_000, XOF)

    def test_accept_twice_is_idempotent_no_double_transfer(
        self, services: AppServices, uow: InMemoryUnitOfWork, transfers: SendP2PTransfer
    ) -> None:
        _user(uow, n=1, msisdn=REQUESTER_MSISDN)
        _user(uow, n=2, msisdn=PAYER_MSISDN, balance=100_000)
        request_id = _create(services)
        uc = AcceptPaymentRequest(services=services, transfers=transfers)
        first = uc.execute(
            AcceptPaymentRequestCommand(payer_user_id=PAYER_ID, request_id=request_id)
        )
        second = uc.execute(
            AcceptPaymentRequestCommand(payer_user_id=PAYER_ID, request_id=request_id)
        )
        assert second.transfer.transfer_id == first.transfer.transfer_id
        payer_wallet = uow.wallets.get_for_user(EntityId(PAYER_ID), XOF)
        assert payer_wallet is not None
        assert payer_wallet.available == Money(100_000 - 15_120, XOF)  # débité une seule fois

    def test_accept_insufficient_funds_keeps_request_pending(
        self, services: AppServices, uow: InMemoryUnitOfWork, transfers: SendP2PTransfer
    ) -> None:
        _user(uow, n=1, msisdn=REQUESTER_MSISDN)
        _user(uow, n=2, msisdn=PAYER_MSISDN, balance=1_000)
        request_id = _create(services)
        with pytest.raises(InsufficientFunds):
            AcceptPaymentRequest(services=services, transfers=transfers).execute(
                AcceptPaymentRequestCommand(payer_user_id=PAYER_ID, request_id=request_id)
            )
        stored = uow.payment_requests.get(EntityId(request_id))
        assert stored is not None and stored.status.value == "PENDING"

    def test_accept_by_wrong_payer_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork, transfers: SendP2PTransfer
    ) -> None:
        _user(uow, n=1, msisdn=REQUESTER_MSISDN)
        _user(uow, n=2, msisdn=PAYER_MSISDN, balance=100_000)
        _user(uow, n=3, msisdn="+2250700000003", balance=100_000)
        request_id = _create(services)
        with pytest.raises(InvalidInput, match="introuvable"):
            AcceptPaymentRequest(services=services, transfers=transfers).execute(
                AcceptPaymentRequestCommand(payer_user_id=str(UUID(int=3)), request_id=request_id)
            )

    def test_accept_expired_request_rejected(
        self,
        services: AppServices,
        uow: InMemoryUnitOfWork,
        transfers: SendP2PTransfer,
        clock: FixedClock,
    ) -> None:
        _user(uow, n=1, msisdn=REQUESTER_MSISDN)
        _user(uow, n=2, msisdn=PAYER_MSISDN, balance=100_000)
        request_id = _create(services)
        clock.advance(days=8)  # TTL = 7 jours
        with pytest.raises(InvalidAccountState, match="expiré"):
            AcceptPaymentRequest(services=services, transfers=transfers).execute(
                AcceptPaymentRequestCommand(payer_user_id=PAYER_ID, request_id=request_id)
            )

    def test_accept_declined_request_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork, transfers: SendP2PTransfer
    ) -> None:
        _user(uow, n=1, msisdn=REQUESTER_MSISDN)
        _user(uow, n=2, msisdn=PAYER_MSISDN, balance=100_000)
        request_id = _create(services)
        DeclinePaymentRequest(services=services).execute(
            DeclinePaymentRequestCommand(payer_user_id=PAYER_ID, request_id=request_id)
        )
        with pytest.raises(InvalidAccountState):
            AcceptPaymentRequest(services=services, transfers=transfers).execute(
                AcceptPaymentRequestCommand(payer_user_id=PAYER_ID, request_id=request_id)
            )


class TestDeclineCancelList:
    def test_decline_marks_declined(self, services: AppServices, uow: InMemoryUnitOfWork) -> None:
        _user(uow, n=1, msisdn=REQUESTER_MSISDN)
        _user(uow, n=2, msisdn=PAYER_MSISDN)
        request_id = _create(services)
        view = DeclinePaymentRequest(services=services).execute(
            DeclinePaymentRequestCommand(payer_user_id=PAYER_ID, request_id=request_id)
        )
        assert view.status == "DECLINED"

    def test_cancel_by_requester(self, services: AppServices, uow: InMemoryUnitOfWork) -> None:
        _user(uow, n=1, msisdn=REQUESTER_MSISDN)
        _user(uow, n=2, msisdn=PAYER_MSISDN)
        request_id = _create(services)
        CancelPaymentRequest(services=services).execute(
            CancelPaymentRequestCommand(requester_user_id=REQUESTER_ID, request_id=request_id)
        )
        stored = uow.payment_requests.get(EntityId(request_id))
        assert stored is not None and stored.status.value == "CANCELLED"

    def test_cancel_unknown_request_rejected(self, services: AppServices) -> None:
        with pytest.raises(InvalidInput, match="introuvable"):
            CancelPaymentRequest(services=services).execute(
                CancelPaymentRequestCommand(
                    requester_user_id=REQUESTER_ID, request_id=str(UUID(int=999))
                )
            )

    def test_decline_unknown_request_rejected(self, services: AppServices) -> None:
        with pytest.raises(InvalidInput, match="introuvable"):
            DeclinePaymentRequest(services=services).execute(
                DeclinePaymentRequestCommand(payer_user_id=PAYER_ID, request_id=str(UUID(int=998)))
            )

    def test_list_incoming_and_outgoing(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow, n=1, msisdn=REQUESTER_MSISDN)
        _user(uow, n=2, msisdn=PAYER_MSISDN)
        request_id = _create(services)

        outgoing = ListPaymentRequests(services=services).execute(
            ListPaymentRequestsCommand(user_id=REQUESTER_ID, box="outgoing")
        )
        incoming = ListPaymentRequests(services=services).execute(
            ListPaymentRequestsCommand(user_id=PAYER_ID, box="incoming")
        )
        assert [r.request_id for r in outgoing] == [request_id]
        assert [r.request_id for r in incoming] == [request_id]
        assert (
            ListPaymentRequests(services=services).execute(
                ListPaymentRequestsCommand(user_id=REQUESTER_ID, box="incoming")
            )
            == []
        )
