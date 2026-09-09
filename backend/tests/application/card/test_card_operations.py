"""Tests des cas d'usage carte : émission, statut, plafonds, données sensibles."""

from __future__ import annotations

from uuid import UUID

import pytest

from flash.application.card.operations import (
    CardView,
    CloseCard,
    CloseCardCommand,
    FreezeCard,
    FreezeCardCommand,
    GetCard,
    GetCardCommand,
    GetCardSensitive,
    GetCardSensitiveCommand,
    IssueCard,
    IssueCardCommand,
    ListCards,
    ListCardsCommand,
    SetCardLimits,
    SetCardLimitsCommand,
    UnfreezeCard,
    UnfreezeCardCommand,
)
from flash.application.services import AppServices
from flash.domain.identity.pin import Pin
from flash.domain.identity.user import User
from flash.domain.shared.errors import InvalidAccountState, InvalidInput
from flash.domain.shared.identifiers import CountryCode, EntityId, Msisdn
from flash.domain.shared.money import XOF
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
def issuer() -> SandboxCardIssuer:
    return SandboxCardIssuer(pepper="test-card-pepper-xyz")


@pytest.fixture
def events() -> RecordingEventPublisher:
    return RecordingEventPublisher()


@pytest.fixture
def services(uow: InMemoryUnitOfWork, events: RecordingEventPublisher) -> AppServices:
    return AppServices(
        uow=lambda: uow,
        clock=FixedClock(),
        ids=SeqIdGenerator(),
        events=events,
        idempotency=InMemoryIdempotencyStore(),
    )


def _user(uow: InMemoryUnitOfWork) -> None:
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
    wallet.pull_events()
    uow.wallets.add(wallet)


def _issue(services: AppServices, issuer: SandboxCardIssuer, **kw: object) -> CardView:
    return IssueCard(services=services, issuer=issuer).execute(
        IssueCardCommand(user_id=USER_ID, **kw)  # type: ignore[arg-type]
    )


class TestIssue:
    def test_issue_then_list_and_get(
        self, services: AppServices, uow: InMemoryUnitOfWork, issuer: SandboxCardIssuer
    ) -> None:
        _user(uow)
        view = _issue(services, issuer, daily_limit_minor=300_000)
        assert view.status == "ACTIVE"
        assert view.masked_pan.endswith(view.last4)
        assert view.daily_limit_minor == 300_000
        assert view.to_dict()["network"] == "VISA"

        listed = ListCards(services=services).execute(ListCardsCommand(user_id=USER_ID))
        assert [c.card_id for c in listed] == [view.card_id]
        got = GetCard(services=services).execute(
            GetCardCommand(user_id=USER_ID, card_id=view.card_id)
        )
        assert got.card_id == view.card_id

    def test_issue_default_limits(
        self, services: AppServices, uow: InMemoryUnitOfWork, issuer: SandboxCardIssuer
    ) -> None:
        _user(uow)
        view = _issue(services, issuer)
        assert view.daily_limit_minor == 500_000
        assert view.monthly_limit_minor == 5_000_000
        assert sorted(view.channels) == ["ATM", "CONTACTLESS", "ECOM"]

    def test_issue_with_channel_subset(
        self, services: AppServices, uow: InMemoryUnitOfWork, issuer: SandboxCardIssuer
    ) -> None:
        _user(uow)
        view = _issue(services, issuer, channels=["ECOM"])
        assert view.channels == ["ECOM"]

    def test_issue_bad_network_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork, issuer: SandboxCardIssuer
    ) -> None:
        _user(uow)
        with pytest.raises(InvalidInput, match=r"[Rr]éseau"):
            _issue(services, issuer, network="AMEX")

    def test_issue_bad_channel_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork, issuer: SandboxCardIssuer
    ) -> None:
        _user(uow)
        with pytest.raises(InvalidInput, match=r"[Cc]anal"):
            _issue(services, issuer, channels=["TAP"])

    def test_get_unknown_card_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow)
        with pytest.raises(InvalidInput, match="introuvable"):
            GetCard(services=services).execute(
                GetCardCommand(user_id=USER_ID, card_id=str(UUID(int=404)))
            )


class TestStatus:
    def test_freeze_unfreeze_close(
        self, services: AppServices, uow: InMemoryUnitOfWork, issuer: SandboxCardIssuer
    ) -> None:
        _user(uow)
        card_id = _issue(services, issuer).card_id
        assert (
            FreezeCard(services=services, issuer=issuer)
            .execute(FreezeCardCommand(user_id=USER_ID, card_id=card_id))
            .status
            == "FROZEN"
        )
        assert (
            UnfreezeCard(services=services, issuer=issuer)
            .execute(UnfreezeCardCommand(user_id=USER_ID, card_id=card_id))
            .status
            == "ACTIVE"
        )
        assert (
            CloseCard(services=services, issuer=issuer)
            .execute(CloseCardCommand(user_id=USER_ID, card_id=card_id))
            .status
            == "CLOSED"
        )

    def test_freeze_other_users_card_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork, issuer: SandboxCardIssuer
    ) -> None:
        _user(uow)
        card_id = _issue(services, issuer).card_id
        with pytest.raises(InvalidInput, match="introuvable"):
            FreezeCard(services=services, issuer=issuer).execute(
                FreezeCardCommand(user_id=str(UUID(int=42)), card_id=card_id)
            )

    def test_set_limits(
        self, services: AppServices, uow: InMemoryUnitOfWork, issuer: SandboxCardIssuer
    ) -> None:
        _user(uow)
        card_id = _issue(services, issuer).card_id
        view = SetCardLimits(services=services).execute(
            SetCardLimitsCommand(
                user_id=USER_ID,
                card_id=card_id,
                daily_limit_minor=200_000,
                monthly_limit_minor=2_000_000,
            )
        )
        assert view.daily_limit_minor == 200_000 and view.monthly_limit_minor == 2_000_000

    def test_set_limits_non_positive_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork, issuer: SandboxCardIssuer
    ) -> None:
        _user(uow)
        card_id = _issue(services, issuer).card_id
        with pytest.raises(InvalidInput, match="strictement positifs"):
            SetCardLimits(services=services).execute(
                SetCardLimitsCommand(
                    user_id=USER_ID, card_id=card_id, daily_limit_minor=0, monthly_limit_minor=10
                )
            )

    def test_set_limits_on_closed_card_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork, issuer: SandboxCardIssuer
    ) -> None:
        _user(uow)
        card_id = _issue(services, issuer).card_id
        CloseCard(services=services, issuer=issuer).execute(
            CloseCardCommand(user_id=USER_ID, card_id=card_id)
        )
        with pytest.raises(InvalidAccountState):
            SetCardLimits(services=services).execute(
                SetCardLimitsCommand(
                    user_id=USER_ID,
                    card_id=card_id,
                    daily_limit_minor=10,
                    monthly_limit_minor=10,
                )
            )


class TestSensitive:
    def test_reveal_returns_pan_and_records_audit(
        self,
        services: AppServices,
        uow: InMemoryUnitOfWork,
        issuer: SandboxCardIssuer,
        events: RecordingEventPublisher,
    ) -> None:
        _user(uow)
        view = _issue(services, issuer)
        secret = GetCardSensitive(services=services, issuer=issuer).execute(
            GetCardSensitiveCommand(user_id=USER_ID, card_id=view.card_id)
        )
        assert secret.pan.endswith(view.last4)
        assert len(secret.cvv) == 3
        assert secret.masked_pan == view.masked_pan
        assert secret.to_dict()["pan"] == secret.pan
        assert "CardSensitiveViewed" in events.names()

    def test_reveal_unknown_card_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork, issuer: SandboxCardIssuer
    ) -> None:
        _user(uow)
        with pytest.raises(InvalidInput, match="introuvable"):
            GetCardSensitive(services=services, issuer=issuer).execute(
                GetCardSensitiveCommand(user_id=USER_ID, card_id=str(UUID(int=7)))
            )


