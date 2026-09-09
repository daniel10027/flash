"""Cas d'usage des clés d'API marchand (BE-069) : émission, liste, révocation."""

from __future__ import annotations

from uuid import UUID

import pytest

from flash.application.merchants.api_keys import (
    IssueMerchantApiKey,
    IssueMerchantApiKeyCommand,
    ListMerchantApiKeys,
    ListMerchantApiKeysCommand,
    RevokeMerchantApiKey,
    RevokeMerchantApiKeyCommand,
)
from flash.application.merchants.operations import NotAMerchant
from flash.application.services import AppServices
from flash.domain.merchants.merchant import Merchant
from flash.domain.shared.errors import InvalidInput
from flash.domain.shared.identifiers import EntityId
from flash.domain.shared.money import XOF
from flash.infrastructure.merchant_api_keys import Sha256MerchantApiKeyVault
from tests.support.fakes import (
    FixedClock,
    InMemoryIdempotencyStore,
    RecordingEventPublisher,
    SeqIdGenerator,
)
from tests.support.repositories import InMemoryUnitOfWork

MID = EntityId(str(UUID(int=9)))
UID = str(UUID(int=9))
VAULT = Sha256MerchantApiKeyVault("test-pepper")


@pytest.fixture
def uow() -> InMemoryUnitOfWork:
    return InMemoryUnitOfWork()


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


def _merchant(uow: InMemoryUnitOfWork) -> None:
    merchant = Merchant.enroll(
        merchant_id=MID,
        user_id=EntityId(UID),
        display_name="Chez Awa",
        category="RESTAURANT",
        currency=XOF,
        fee_bps=100,
        now=FixedClock().now(),
    )
    merchant.pull_events()
    uow.merchants.add(merchant)


def _issue(services: AppServices, label: str = "Caisse") -> str:
    view = IssueMerchantApiKey(services=services, vault=VAULT).execute(
        IssueMerchantApiKeyCommand(merchant_user_id=UID, label=label)
    )
    return view.key.key_id


class TestIssue:
    def test_issue_returns_secret_once_and_persists_hash(
        self, services: AppServices, uow: InMemoryUnitOfWork, events: RecordingEventPublisher
    ) -> None:
        _merchant(uow)
        view = IssueMerchantApiKey(services=services, vault=VAULT).execute(
            IssueMerchantApiKeyCommand(merchant_user_id=UID, label="Caisse 1")
        )
        assert view.secret.startswith("mk_")
        assert view.key.prefix in view.secret
        assert view.to_dict()["secret"] == view.secret
        stored = uow.merchant_api_keys.list_for_merchant(MID)
        assert len(stored) == 1
        assert stored[0].secret_hash != view.secret
        assert VAULT.matches(view.secret, stored[0].secret_hash)
        assert "MerchantApiKeyIssued" in events.names()

    def test_non_merchant_rejected(self, services: AppServices) -> None:
        with pytest.raises(NotAMerchant):
            _issue(services)

    def test_cap_of_ten_active_keys(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _merchant(uow)
        for _ in range(10):
            _issue(services)
        with pytest.raises(InvalidInput, match="Trop de clés"):
            _issue(services)

    def test_revoked_keys_do_not_count_towards_cap(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _merchant(uow)
        first = _issue(services)
        for _ in range(9):
            _issue(services)
        RevokeMerchantApiKey(services=services).execute(
            RevokeMerchantApiKeyCommand(merchant_user_id=UID, key_id=first)
        )
        _issue(services)  # ne lève pas


class TestListAndRevoke:
    def test_list_shows_prefix_only(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _merchant(uow)
        _issue(services, "A")
        rows = ListMerchantApiKeys(services=services).execute(
            ListMerchantApiKeysCommand(merchant_user_id=UID)
        )
        assert len(rows) == 1
        assert rows[0].revoked is False
        assert "secret" not in rows[0].to_dict()

    def test_list_non_merchant_rejected(self, services: AppServices) -> None:
        with pytest.raises(NotAMerchant):
            ListMerchantApiKeys(services=services).execute(
                ListMerchantApiKeysCommand(merchant_user_id=UID)
            )

    def test_revoke(
        self, services: AppServices, uow: InMemoryUnitOfWork, events: RecordingEventPublisher
    ) -> None:
        _merchant(uow)
        key_id = _issue(services)
        view = RevokeMerchantApiKey(services=services).execute(
            RevokeMerchantApiKeyCommand(merchant_user_id=UID, key_id=key_id)
        )
        assert view.revoked is True
        assert "MerchantApiKeyRevoked" in events.names()

    def test_revoke_non_merchant_rejected(self, services: AppServices) -> None:
        with pytest.raises(NotAMerchant):
            RevokeMerchantApiKey(services=services).execute(
                RevokeMerchantApiKeyCommand(merchant_user_id=UID, key_id=str(UUID(int=1)))
            )

    def test_revoke_unknown_key_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _merchant(uow)
        with pytest.raises(InvalidInput, match="introuvable"):
            RevokeMerchantApiKey(services=services).execute(
                RevokeMerchantApiKeyCommand(
                    merchant_user_id=UID, key_id=str(UUID(int=404))
                )
            )

    def test_revoke_malformed_key_id_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _merchant(uow)
        with pytest.raises(InvalidInput, match="introuvable"):
            RevokeMerchantApiKey(services=services).execute(
                RevokeMerchantApiKeyCommand(merchant_user_id=UID, key_id="not-a-uuid")
            )

    def test_revoke_key_of_other_merchant_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _merchant(uow)
        other = Merchant.enroll(
            merchant_id=EntityId(str(UUID(int=8))),
            user_id=EntityId(str(UUID(int=8))),
            display_name="Autre",
            category="GENERAL",
            currency=XOF,
            fee_bps=100,
            now=FixedClock().now(),
        )
        other.pull_events()
        uow.merchants.add(other)
        key_id = _issue(services)
        with pytest.raises(InvalidInput, match="introuvable"):
            RevokeMerchantApiKey(services=services).execute(
                RevokeMerchantApiKeyCommand(
                    merchant_user_id=str(UUID(int=8)), key_id=key_id
                )
            )
