"""Tests du flux d'autorisation carte (BE-057) : authorize / capture / reverse / refund."""

from __future__ import annotations

from uuid import UUID

import pytest

from flash.application.card.authorizations import (
    AuthorizeCardPayment,
    AuthorizeCardPaymentCommand,
    CaptureCardPayment,
    CaptureCardPaymentCommand,
    RefundCardPayment,
    RefundCardPaymentCommand,
    ReverseCardAuthorization,
    ReverseCardAuthorizationCommand,
)
from flash.application.card.operations import IssueCard, IssueCardCommand
from flash.application.services import AppServices
from flash.application.statement.queries import ListStatement, ListStatementCommand
from flash.domain.identity.pin import Pin
from flash.domain.identity.user import User
from flash.domain.ledger.transaction import TransactionKind, sum_postings
from flash.domain.shared.errors import InvalidInput
from flash.domain.shared.identifiers import CountryCode, EntityId, Msisdn
from flash.domain.shared.money import XOF, Money
from flash.domain.wallet.wallet import Wallet
from flash.infrastructure.card_issuer import SandboxCardIssuer
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
MSISDN = "+2250700000001"


@pytest.fixture
def uow() -> InMemoryUnitOfWork:
    return InMemoryUnitOfWork()


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock()


@pytest.fixture
def events() -> RecordingEventPublisher:
    return RecordingEventPublisher()


@pytest.fixture
def issuer() -> SandboxCardIssuer:
    return SandboxCardIssuer(pepper="test-card-pepper-auth")


@pytest.fixture
def services(
    uow: InMemoryUnitOfWork, clock: FixedClock, events: RecordingEventPublisher
) -> AppServices:
    return AppServices(
        uow=lambda: uow,
        clock=clock,
        ids=SeqIdGenerator(),
        events=events,
        idempotency=InMemoryIdempotencyStore(),
    )


def _make(
    services: AppServices,
    uow: InMemoryUnitOfWork,
    issuer: SandboxCardIssuer,
    *,
    balance: int = 200_000,
    daily_limit_minor: int | None = None,
    channels: list[str] | None = None,
) -> str:
    user = User.register(
        user_id=EntityId(USER_ID),
        country=CI,
        msisdn=Msisdn(MSISDN),
        pin_hash=FakePinHasher().hash(Pin("1397")),
        now=FixedClock().now(),
    )
    user.activate(FixedClock().now())
    user.pull_events()
    uow.users.add(user)
    wallet = Wallet.open(
        wallet_id=EntityId(str(UUID(int=500))),
        user_id=user.id,
        currency=XOF,
        now=FixedClock().now(),
    )
    if balance:
        wallet.credit(Money(balance, XOF), FixedClock().now())
    wallet.pull_events()
    uow.wallets.add(wallet)
    view = IssueCard(services=services, issuer=issuer).execute(
        IssueCardCommand(
            user_id=USER_ID, daily_limit_minor=daily_limit_minor, channels=channels
        )
    )
    card = uow.cards.get(EntityId(view.card_id))
    assert card is not None
    return card.pan_token


def _authorize(
    services: AppServices, token: str, *, authorization_id: str, amount: int, channel: str = "ECOM"
) -> AuthorizeCardPaymentCommand:
    return AuthorizeCardPaymentCommand(
        authorization_id=authorization_id,
        pan_token=token,
        amount_minor=amount,
        channel=channel,
        merchant_name="Boutique",
    )


class TestAuthorize:
    def test_approved_reserves_funds(
        self, services: AppServices, uow: InMemoryUnitOfWork, issuer: SandboxCardIssuer
    ) -> None:
        token = _make(services, uow, issuer)
        decision = AuthorizeCardPayment(services=services).execute(
            _authorize(services, token, authorization_id="cardauth-0001", amount=30_000)
        )
        assert decision.decision == "APPROVED" and decision.reason is None
        wallet = uow.wallets.get_for_user(EntityId(USER_ID), XOF)
        assert wallet is not None
        assert wallet.available == Money(170_000, XOF)
        assert wallet.reserved == Money(30_000, XOF)
        assert uow.ledger.transactions == []  # aucune écriture à l'autorisation

    def test_replay_same_authorization_id(
        self, services: AppServices, uow: InMemoryUnitOfWork, issuer: SandboxCardIssuer
    ) -> None:
        token = _make(services, uow, issuer)
        cmd = _authorize(services, token, authorization_id="cardauth-rep", amount=30_000)
        first = AuthorizeCardPayment(services=services).execute(cmd)
        second = AuthorizeCardPayment(services=services).execute(cmd)
        assert first.decision == second.decision == "APPROVED"
        wallet = uow.wallets.get_for_user(EntityId(USER_ID), XOF)
        assert wallet is not None and wallet.reserved == Money(30_000, XOF)  # réservé une fois

    def test_replay_after_capture_stays_approved(
        self, services: AppServices, uow: InMemoryUnitOfWork, issuer: SandboxCardIssuer
    ) -> None:
        token = _make(services, uow, issuer)
        cmd = _authorize(services, token, authorization_id="cardauth-postcap", amount=30_000)
        AuthorizeCardPayment(services=services).execute(cmd)
        CaptureCardPayment(services=services).execute(
            CaptureCardPaymentCommand(authorization_id="cardauth-postcap")
        )
        again = AuthorizeCardPayment(services=services).execute(cmd)
        assert again.decision == "APPROVED"

    def test_unknown_card_declined(self, services: AppServices, uow: InMemoryUnitOfWork) -> None:
        decision = AuthorizeCardPayment(services=services).execute(
            AuthorizeCardPaymentCommand(
                authorization_id="cardauth-nocard",
                pan_token="tok_does_not_exist",
                amount_minor=1_000,
                channel="ECOM",
            )
        )
        assert decision.decision == "DECLINED" and decision.reason == "CARD_NOT_FOUND"

    def test_disabled_channel_declined(
        self, services: AppServices, uow: InMemoryUnitOfWork, issuer: SandboxCardIssuer
    ) -> None:
        token = _make(services, uow, issuer, channels=["ECOM"])
        decision = AuthorizeCardPayment(services=services).execute(
            _authorize(
                services, token, authorization_id="cardauth-atm", amount=1_000, channel="ATM"
            )
        )
        assert decision.decision == "DECLINED" and decision.reason == "CHANNEL_DISABLED"

    def test_limit_declined(
        self, services: AppServices, uow: InMemoryUnitOfWork, issuer: SandboxCardIssuer
    ) -> None:
        token = _make(services, uow, issuer, daily_limit_minor=25_000)
        decision = AuthorizeCardPayment(services=services).execute(
            _authorize(services, token, authorization_id="cardauth-lim", amount=30_000)
        )
        assert decision.decision == "DECLINED" and decision.reason == "CARD_LIMIT_REACHED"
        wallet = uow.wallets.get_for_user(EntityId(USER_ID), XOF)
        assert wallet is not None and wallet.reserved == Money(0, XOF)

    def test_insufficient_funds_declined(
        self, services: AppServices, uow: InMemoryUnitOfWork, issuer: SandboxCardIssuer
    ) -> None:
        token = _make(services, uow, issuer, balance=10_000)
        decision = AuthorizeCardPayment(services=services).execute(
            _authorize(services, token, authorization_id="cardauth-broke", amount=30_000)
        )
        assert decision.decision == "DECLINED" and decision.reason == "INSUFFICIENT_FUNDS"
        wallet = uow.wallets.get_for_user(EntityId(USER_ID), XOF)
        assert wallet is not None and wallet.reserved == Money(0, XOF)

    def test_short_authorization_id_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork, issuer: SandboxCardIssuer
    ) -> None:
        token = _make(services, uow, issuer)
        with pytest.raises(InvalidInput):
            AuthorizeCardPayment(services=services).execute(
                _authorize(services, token, authorization_id="short", amount=1_000)
            )

    def test_bad_channel_string_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork, issuer: SandboxCardIssuer
    ) -> None:
        token = _make(services, uow, issuer)
        with pytest.raises(InvalidInput, match=r"[Cc]anal"):
            AuthorizeCardPayment(services=services).execute(
                _authorize(
                    services,
                    token,
                    authorization_id="cardauth-badchan",
                    amount=1_000,
                    channel="TAP",
                )
            )

    def test_non_positive_amount_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork, issuer: SandboxCardIssuer
    ) -> None:
        token = _make(services, uow, issuer)
        with pytest.raises(InvalidInput, match="strictement positif"):
            AuthorizeCardPayment(services=services).execute(
                _authorize(services, token, authorization_id="cardauth-zero", amount=0)
            )


class TestCapture:
    def test_full_capture_settles_and_writes_ledger(
        self, services: AppServices, uow: InMemoryUnitOfWork, issuer: SandboxCardIssuer
    ) -> None:
        token = _make(services, uow, issuer)
        AuthorizeCardPayment(services=services).execute(
            _authorize(services, token, authorization_id="cardauth-cap", amount=30_000)
        )
        result = CaptureCardPayment(services=services).execute(
            CaptureCardPaymentCommand(authorization_id="cardauth-cap")
        )
        assert result.status == "CAPTURED" and result.amount_minor == 30_000
        wallet = uow.wallets.get_for_user(EntityId(USER_ID), XOF)
        assert wallet is not None
        assert wallet.available == Money(170_000, XOF)
        assert wallet.reserved == Money(0, XOF)
        assert wallet.balance == Money(170_000, XOF)
        [txn] = uow.ledger.transactions
        assert txn.kind is TransactionKind.CARD_CAPTURE
        assert txn.is_balanced and sum_postings(txn.postings) == {"XOF": 0}

    def test_partial_capture_releases_remainder(
        self, services: AppServices, uow: InMemoryUnitOfWork, issuer: SandboxCardIssuer
    ) -> None:
        token = _make(services, uow, issuer)
        AuthorizeCardPayment(services=services).execute(
            _authorize(services, token, authorization_id="cardauth-pc", amount=30_000)
        )
        CaptureCardPayment(services=services).execute(
            CaptureCardPaymentCommand(authorization_id="cardauth-pc", amount_minor=18_000)
        )
        wallet = uow.wallets.get_for_user(EntityId(USER_ID), XOF)
        assert wallet is not None
        assert wallet.reserved == Money(0, XOF)
        assert wallet.available == Money(182_000, XOF)

    def test_capture_replay(
        self, services: AppServices, uow: InMemoryUnitOfWork, issuer: SandboxCardIssuer
    ) -> None:
        token = _make(services, uow, issuer)
        AuthorizeCardPayment(services=services).execute(
            _authorize(services, token, authorization_id="cardauth-cr", amount=30_000)
        )
        first = CaptureCardPayment(services=services).execute(
            CaptureCardPaymentCommand(authorization_id="cardauth-cr")
        )
        second = CaptureCardPayment(services=services).execute(
            CaptureCardPaymentCommand(authorization_id="cardauth-cr")
        )
        assert first == second
        assert len(uow.ledger.transactions) == 1

    def test_capture_unknown_rejected(self, services: AppServices) -> None:
        with pytest.raises(InvalidInput, match="introuvable"):
            CaptureCardPayment(services=services).execute(
                CaptureCardPaymentCommand(authorization_id="cardauth-missing")
            )

    def test_capture_appears_in_statement(
        self, services: AppServices, uow: InMemoryUnitOfWork, issuer: SandboxCardIssuer
    ) -> None:
        token = _make(services, uow, issuer)
        AuthorizeCardPayment(services=services).execute(
            _authorize(services, token, authorization_id="cardauth-st", amount=30_000)
        )
        CaptureCardPayment(services=services).execute(
            CaptureCardPaymentCommand(authorization_id="cardauth-st")
        )
        page = ListStatement(services=services).execute(ListStatementCommand(user_id=USER_ID))
        [line] = page.lines
        assert line.kind == "CARD_CAPTURE" and line.direction == "out"
        assert line.amount_minor == 30_000 and line.counterparty_masked == "Boutique"


class TestReverseRefund:
    def test_reverse_releases_reservation(
        self, services: AppServices, uow: InMemoryUnitOfWork, issuer: SandboxCardIssuer
    ) -> None:
        token = _make(services, uow, issuer)
        AuthorizeCardPayment(services=services).execute(
            _authorize(services, token, authorization_id="cardauth-rev", amount=30_000)
        )
        result = ReverseCardAuthorization(services=services).execute(
            ReverseCardAuthorizationCommand(authorization_id="cardauth-rev")
        )
        assert result.status == "REVERSED"
        wallet = uow.wallets.get_for_user(EntityId(USER_ID), XOF)
        assert wallet is not None
        assert wallet.available == Money(200_000, XOF) and wallet.reserved == Money(0, XOF)
        assert uow.ledger.transactions == []

    def test_reverse_replay(
        self, services: AppServices, uow: InMemoryUnitOfWork, issuer: SandboxCardIssuer
    ) -> None:
        token = _make(services, uow, issuer)
        AuthorizeCardPayment(services=services).execute(
            _authorize(services, token, authorization_id="cardauth-rr", amount=30_000)
        )
        ReverseCardAuthorization(services=services).execute(
            ReverseCardAuthorizationCommand(authorization_id="cardauth-rr")
        )
        again = ReverseCardAuthorization(services=services).execute(
            ReverseCardAuthorizationCommand(authorization_id="cardauth-rr")
        )
        assert again.status == "REVERSED"

    def test_refund_after_capture_credits_wallet(
        self, services: AppServices, uow: InMemoryUnitOfWork, issuer: SandboxCardIssuer
    ) -> None:
        token = _make(services, uow, issuer)
        AuthorizeCardPayment(services=services).execute(
            _authorize(services, token, authorization_id="cardauth-rf", amount=30_000)
        )
        CaptureCardPayment(services=services).execute(
            CaptureCardPaymentCommand(authorization_id="cardauth-rf")
        )
        result = RefundCardPayment(services=services).execute(
            RefundCardPaymentCommand(authorization_id="cardauth-rf")
        )
        assert result.status == "REFUNDED" and result.amount_minor == 30_000
        wallet = uow.wallets.get_for_user(EntityId(USER_ID), XOF)
        assert wallet is not None
        assert wallet.available == Money(200_000, XOF)
        assert wallet.balance == Money(200_000, XOF)
        kinds = {t.kind for t in uow.ledger.transactions}
        assert kinds == {TransactionKind.CARD_CAPTURE, TransactionKind.CARD_REFUND}
        for t in uow.ledger.transactions:
            assert t.is_balanced

    def test_refund_replay(
        self, services: AppServices, uow: InMemoryUnitOfWork, issuer: SandboxCardIssuer
    ) -> None:
        token = _make(services, uow, issuer)
        AuthorizeCardPayment(services=services).execute(
            _authorize(services, token, authorization_id="cardauth-rfr", amount=30_000)
        )
        CaptureCardPayment(services=services).execute(
            CaptureCardPaymentCommand(authorization_id="cardauth-rfr")
        )
        first = RefundCardPayment(services=services).execute(
            RefundCardPaymentCommand(authorization_id="cardauth-rfr")
        )
        second = RefundCardPayment(services=services).execute(
            RefundCardPaymentCommand(authorization_id="cardauth-rfr")
        )
        assert first == second
        assert sum(1 for t in uow.ledger.transactions if t.kind is TransactionKind.CARD_REFUND) == 1
