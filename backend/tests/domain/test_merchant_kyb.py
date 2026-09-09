"""Tests KYB de l'agrégat ``Merchant`` et de l'entité ``MerchantApiKey`` (BE-069)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from flash.domain.merchants.api_key import MerchantApiKey
from flash.domain.merchants.merchant import KybStatus, Merchant, MerchantStatus
from flash.domain.shared.errors import InvalidAccountState, InvalidInput
from flash.domain.shared.identifiers import EntityId
from flash.domain.shared.money import XOF

T0 = datetime(2026, 1, 1, tzinfo=UTC)
MID = EntityId(str(UUID(int=1)))
UID = EntityId(str(UUID(int=2)))
KID = EntityId(str(UUID(int=3)))


def _merchant() -> Merchant:
    return Merchant(
        id=MID,
        user_id=UID,
        display_name="Chez Awa",
        category="RESTAURANT",
        currency=XOF,
        fee_bps=100,
        created_at=T0,
        status=MerchantStatus.ACTIVE,
    )


class TestMerchantKyb:
    def test_default_is_pending(self) -> None:
        assert _merchant().kyb_status is KybStatus.PENDING
        assert _merchant().kyb_approved is False

    def test_submit_records_event(self) -> None:
        merchant = _merchant()
        merchant.submit_kyb(T0)
        assert merchant.kyb_status is KybStatus.PENDING
        assert [e.name for e in merchant.pull_events()] == ["MerchantKybSubmitted"]

    def test_submit_after_approved_is_rejected(self) -> None:
        merchant = _merchant()
        merchant.approve_kyb(reviewer="key:compliance", now=T0)
        with pytest.raises(InvalidAccountState, match="déjà vérifié"):
            merchant.submit_kyb(T0)

    def test_approve_sets_status_and_event(self) -> None:
        merchant = _merchant()
        merchant.approve_kyb(reviewer="key:admin", now=T0)
        assert merchant.kyb_status is KybStatus.APPROVED
        assert merchant.kyb_approved is True
        assert merchant.kyb_reviewed_at == T0
        assert [e.name for e in merchant.pull_events()] == ["MerchantKybApproved"]

    def test_approve_is_idempotent(self) -> None:
        merchant = _merchant()
        merchant.approve_kyb(reviewer="r", now=T0)
        merchant.pull_events()
        merchant.approve_kyb(reviewer="r", now=T0)
        assert merchant.pull_events() == []

    def test_reject_requires_reason(self) -> None:
        with pytest.raises(InvalidInput, match="motif"):
            _merchant().reject_kyb(reviewer="r", reason="  ", now=T0)

    def test_reject_sets_reason_and_event(self) -> None:
        merchant = _merchant()
        merchant.reject_kyb(reviewer="key:compliance", reason="RCCM manquant", now=T0)
        assert merchant.kyb_status is KybStatus.REJECTED
        assert merchant.kyb_reason == "RCCM manquant"
        assert [e.name for e in merchant.pull_events()] == ["MerchantKybRejected"]

    def test_resubmit_after_reject_clears_reason(self) -> None:
        merchant = _merchant()
        merchant.reject_kyb(reviewer="r", reason="doc", now=T0)
        merchant.submit_kyb(T0)
        assert merchant.kyb_status is KybStatus.PENDING
        assert merchant.kyb_reason is None

    def test_ensure_kyb_approved_guard(self) -> None:
        merchant = _merchant()
        with pytest.raises(InvalidAccountState, match="KYB"):
            merchant.ensure_kyb_approved()
        merchant.approve_kyb(reviewer="r", now=T0)
        merchant.ensure_kyb_approved()


class TestMerchantApiKey:
    def test_issue_records_event_and_defaults(self) -> None:
        key = MerchantApiKey.issue(
            key_id=KID,
            merchant_id=MID,
            prefix="abcd1234",
            secret_hash="x" * 64,
            label="",
            now=T0,
        )
        assert key.is_active is True
        assert key.label == "sans nom"
        assert [e.name for e in key.pull_events()] == ["MerchantApiKeyIssued"]

    def test_issue_rejects_too_long_label(self) -> None:
        with pytest.raises(InvalidInput, match="trop long"):
            MerchantApiKey.issue(
                key_id=KID,
                merchant_id=MID,
                prefix="abcd1234",
                secret_hash="x" * 64,
                label="z" * 61,
                now=T0,
            )

    def test_constructor_rejects_blank_prefix_or_hash(self) -> None:
        with pytest.raises(InvalidInput, match="Préfixe"):
            MerchantApiKey(
                id=KID, merchant_id=MID, prefix="  ", secret_hash="x", label="l", created_at=T0
            )
        with pytest.raises(InvalidInput, match="Empreinte"):
            MerchantApiKey(
                id=KID, merchant_id=MID, prefix="p", secret_hash="  ", label="l", created_at=T0
            )

    def test_mark_used(self) -> None:
        key = MerchantApiKey.issue(
            key_id=KID, merchant_id=MID, prefix="p", secret_hash="h", label="l", now=T0
        )
        key.mark_used(T0)
        assert key.last_used_at == T0

    def test_revoke_once(self) -> None:
        key = MerchantApiKey.issue(
            key_id=KID, merchant_id=MID, prefix="p", secret_hash="h", label="l", now=T0
        )
        key.pull_events()
        key.revoke(T0)
        assert key.is_active is False
        assert [e.name for e in key.pull_events()] == ["MerchantApiKeyRevoked"]
        with pytest.raises(InvalidAccountState, match="déjà révoquée"):
            key.revoke(T0)

    def test_repr(self) -> None:
        key = MerchantApiKey.issue(
            key_id=KID, merchant_id=MID, prefix="p", secret_hash="h", label="l", now=T0
        )
        assert "active" in repr(key)
        key.revoke(T0)
        assert "révoquée" in repr(key)
