"""Tests de l'agrégat PaymentRequest (BE-032)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from flash.domain.payments.request import PaymentRequest, PaymentRequestStatus
from flash.domain.shared.errors import InvalidAccountState, InvalidInput
from flash.domain.shared.identifiers import EntityId
from flash.domain.shared.money import XOF, Currency, Money

T0 = datetime(2026, 1, 1, tzinfo=UTC)
REQ = EntityId(str(UUID(int=1)))
REQUESTER = EntityId(str(UUID(int=2)))
PAYER = EntityId(str(UUID(int=3)))
TRANSFER = EntityId(str(UUID(int=4)))


def _open(**kw: object) -> PaymentRequest:
    params: dict[str, object] = {
        "request_id": REQ,
        "requester_id": REQUESTER,
        "payer_id": PAYER,
        "amount": Money(15_000, XOF),
        "now": T0,
        "expires_at": T0 + timedelta(days=7),
        "note": "Déjeuner",
    }
    params.update(kw)
    return PaymentRequest.open(**params)  # type: ignore[arg-type]


class TestOpen:
    def test_open_is_pending_and_records_event(self) -> None:
        req = _open()
        assert req.status is PaymentRequestStatus.PENDING
        assert req.note == "Déjeuner"
        assert [e.name for e in req.pull_events()] == ["PaymentRequestCreated"]

    def test_self_request_rejected(self) -> None:
        with pytest.raises(InvalidInput, match="soi-même"):
            _open(payer_id=REQUESTER)

    def test_non_positive_amount_rejected(self) -> None:
        with pytest.raises(ValueError, match="strictement positif"):
            _open(amount=Money(0, XOF))

    def test_currency_mismatch_rejected(self) -> None:
        with pytest.raises(ValueError, match="Devise"):
            PaymentRequest(
                id=REQ,
                requester_id=REQUESTER,
                payer_id=PAYER,
                amount=Money(1, Currency.of("EUR")),
                currency_code="XOF",
                status=PaymentRequestStatus.PENDING,
                created_at=T0,
                expires_at=T0 + timedelta(days=7),
            )


class TestTransitions:
    def test_accept_sets_transfer_and_event(self) -> None:
        req = _open()
        req.pull_events()
        req.accept(transfer_id=TRANSFER, now=T0)
        assert req.status is PaymentRequestStatus.ACCEPTED
        assert req.resulting_transfer_id == TRANSFER
        assert [e.name for e in req.pull_events()] == ["PaymentRequestAccepted"]

    def test_decline_and_cancel_are_terminal(self) -> None:
        req = _open()
        req.pull_events()
        req.decline(T0)
        assert req.status is PaymentRequestStatus.DECLINED
        assert [e.name for e in req.pull_events()] == ["PaymentRequestDeclined"]
        with pytest.raises(InvalidAccountState):
            req.cancel(T0)

    def test_cancel_from_pending(self) -> None:
        req = _open()
        req.pull_events()
        req.cancel(T0)
        assert req.status is PaymentRequestStatus.CANCELLED
        assert [e.name for e in req.pull_events()] == ["PaymentRequestCancelled"]

    def test_accept_after_expiry_rejected(self) -> None:
        req = _open()
        with pytest.raises(InvalidAccountState, match="expiré"):
            req.accept(transfer_id=TRANSFER, now=T0 + timedelta(days=8))

    def test_accept_twice_rejected(self) -> None:
        req = _open()
        req.accept(transfer_id=TRANSFER, now=T0)
        with pytest.raises(InvalidAccountState, match="plus en attente"):
            req.accept(transfer_id=TRANSFER, now=T0)

    def test_expire_only_from_pending(self) -> None:
        req = _open()
        req.pull_events()
        req.expire(T0)
        assert req.status is PaymentRequestStatus.EXPIRED
        assert [e.name for e in req.pull_events()] == ["PaymentRequestExpired"]
        req.expire(T0)  # no-op
        assert req.pull_events() == []

    def test_repr(self) -> None:
        assert "status=PENDING" in repr(_open())
