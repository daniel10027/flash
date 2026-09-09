"""Tests du job de rapprochement carte (BE-059)."""

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
)
from flash.application.card.operations import IssueCard, IssueCardCommand
from flash.application.jobs.card_reconcile import ReconcileCardSettlements
from flash.application.services import AppServices
from flash.domain.identity.pin import Pin
from flash.domain.identity.user import User
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


@pytest.fixture
def uow() -> InMemoryUnitOfWork:
    return InMemoryUnitOfWork()


@pytest.fixture
def services(uow: InMemoryUnitOfWork) -> AppServices:
    return AppServices(
        uow=lambda: uow,
        clock=FixedClock(),
        ids=SeqIdGenerator(),
        events=RecordingEventPublisher(),
        idempotency=InMemoryIdempotencyStore(),
    )


def _card_token(services: AppServices, uow: InMemoryUnitOfWork, issuer: SandboxCardIssuer) -> str:
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
    wallet = Wallet.open(
        wallet_id=EntityId(str(UUID(int=500))),
        user_id=user.id,
        currency=XOF,
        now=FixedClock().now(),
    )
    wallet.credit(Money(200_000, XOF), FixedClock().now())
    wallet.pull_events()
    uow.wallets.add(wallet)
    view = IssueCard(services=services, issuer=issuer).execute(IssueCardCommand(user_id=USER_ID))
    card = uow.cards.get(EntityId(view.card_id))
    assert card is not None
    return card.pan_token


def _auth_capture(services: AppServices, token: str, auth_id: str, amount: int) -> None:
    AuthorizeCardPayment(services=services).execute(
        AuthorizeCardPaymentCommand(
            authorization_id=auth_id, pan_token=token, amount_minor=amount, channel="ECOM"
        )
    )
    CaptureCardPayment(services=services).execute(CaptureCardPaymentCommand(authorization_id=auth_id))


def test_clean_when_ledger_matches(services: AppServices, uow: InMemoryUnitOfWork) -> None:
    issuer = SandboxCardIssuer(pepper="rec-pepper")
    token = _card_token(services, uow, issuer)
    _auth_capture(services, token, "cardauth-rec-1", 30_000)
    _auth_capture(services, token, "cardauth-rec-2", 12_000)
    RefundCardPayment(services=services).execute(
        RefundCardPaymentCommand(authorization_id="cardauth-rec-2")
    )

    report = ReconcileCardSettlements(services=services).execute()
    assert report.checked == 2
    assert report.ok is True
    assert report.to_dict()["discrepancies"] == []


def test_noop_when_no_resolved_authorizations(
    services: AppServices, uow: InMemoryUnitOfWork
) -> None:
    report = ReconcileCardSettlements(services=services).execute()
    assert report.checked == 0 and report.ok is True


def test_paginates_across_pages(
    services: AppServices, uow: InMemoryUnitOfWork, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("flash.application.jobs.card_reconcile._PAGE", 1)
    issuer = SandboxCardIssuer(pepper="rec-pepper-pg")
    token = _card_token(services, uow, issuer)
    _auth_capture(services, token, "cardauth-pg-1", 10_000)
    _auth_capture(services, token, "cardauth-pg-2", 20_000)
    report = ReconcileCardSettlements(services=services).execute()
    assert report.checked == 2 and report.ok is True


def test_detects_amount_mismatch(services: AppServices, uow: InMemoryUnitOfWork) -> None:
    issuer = SandboxCardIssuer(pepper="rec-pepper-mm")
    token = _card_token(services, uow, issuer)
    _auth_capture(services, token, "cardauth-mm-1", 30_000)
    auth = uow.card_authorizations.get_by_authorization_id("cardauth-mm-1")
    assert auth is not None
    auth.captured_minor = 99_999  # la projection ne colle plus au ledger

    report = ReconcileCardSettlements(services=services).execute()
    assert report.ok is False
    assert "net" in report.discrepancies[0].issue


def test_detects_missing_capture_entry(services: AppServices, uow: InMemoryUnitOfWork) -> None:
    issuer = SandboxCardIssuer(pepper="rec-pepper-2")
    token = _card_token(services, uow, issuer)
    _auth_capture(services, token, "cardauth-bad-1", 30_000)

    # on casse la piste ledger : suppression de l'écriture de capture
    uow.ledger._by_id.clear()  # type: ignore[attr-defined]

    report = ReconcileCardSettlements(services=services).execute()
    assert report.ok is False
    [d] = report.discrepancies
    assert d.authorization_id == "cardauth-bad-1"
    assert "capture" in d.issue
    assert report.to_dict()["discrepancies"][0]["issue"] == d.issue
