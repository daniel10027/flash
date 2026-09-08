"""Tests du NotificationDispatcher : événement de domaine -> notification(s) (BE-040)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from flash.application.notifications.dispatcher import NotificationDispatcher
from flash.application.notifications.model import NotificationKind
from flash.domain.cash.events import CashDepositCompleted, CashWithdrawalConfirmed
from flash.domain.identity.events import KycCaseApproved, KycCaseRejected
from flash.domain.merchants.events import MerchantPaymentCompleted, MerchantPaymentRefunded
from flash.domain.shared.events import DomainEvent
from flash.domain.wallet.events import TransferCompleted, TransferReversed
from tests.support.fakes import FixedClock, SeqIdGenerator
from tests.support.notifications import RecordingNotifier

T0 = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture
def notifier() -> RecordingNotifier:
    return RecordingNotifier()


@pytest.fixture
def dispatcher(notifier: RecordingNotifier) -> NotificationDispatcher:
    return NotificationDispatcher(notifier=notifier, clock=FixedClock(), ids=SeqIdGenerator())


def test_transfer_completed_notifies_both_parties(
    dispatcher: NotificationDispatcher, notifier: RecordingNotifier
) -> None:
    dispatcher.handle(
        [
            TransferCompleted(
                occurred_at=T0,
                aggregate_id="txn-1",
                sender_id="u-sender",
                recipient_id="u-recipient",
                amount_minor=10_000,
                fee_minor=80,
                currency="XOF",
                reference="TRX-1",
            )
        ]
    )
    assert {n.user_id for n in notifier.delivered} == {"u-sender", "u-recipient"}
    inbound = notifier.for_user("u-recipient")[0]
    assert inbound.kind is NotificationKind.MONEY_IN
    assert "10 000 XOF" in inbound.body
    outbound = notifier.for_user("u-sender")[0]
    assert outbound.kind is NotificationKind.MONEY_OUT
    assert outbound.data["reference"] == "TRX-1"


def test_transfer_reversed_notifies_both_parties(
    dispatcher: NotificationDispatcher, notifier: RecordingNotifier
) -> None:
    dispatcher.handle(
        [
            TransferReversed(
                occurred_at=T0,
                aggregate_id="rev-1",
                original_transfer_id="txn-1",
                sender_id="u-sender",
                recipient_id="u-recipient",
                amount_minor=10_000,
                fee_minor=80,
                currency="XOF",
                reference="TRX-1",
            )
        ]
    )
    assert {n.kind for n in notifier.delivered} == {NotificationKind.REVERSAL}
    assert len(notifier.delivered) == 2


def test_cash_events_notify_client(
    dispatcher: NotificationDispatcher, notifier: RecordingNotifier
) -> None:
    dispatcher.handle(
        [
            CashDepositCompleted(
                occurred_at=T0,
                aggregate_id="dep-1",
                client_id="u-client",
                agent_id="u-agent",
                amount_minor=40_000,
                currency="XOF",
            ),
            CashWithdrawalConfirmed(
                occurred_at=T0,
                aggregate_id="wdl-1",
                client_id="u-client",
                agent_id="u-agent",
                amount_minor=30_000,
                fee_minor=0,
                currency="XOF",
            ),
        ]
    )
    kinds = [n.kind for n in notifier.for_user("u-client")]
    assert kinds == [NotificationKind.CASH_DEPOSIT, NotificationKind.CASH_WITHDRAWAL]
    assert notifier.for_user("u-agent") == []


def test_merchant_events_notify_payer(
    dispatcher: NotificationDispatcher, notifier: RecordingNotifier
) -> None:
    dispatcher.handle(
        [
            MerchantPaymentCompleted(
                occurred_at=T0,
                aggregate_id="pay-1",
                payer_id="u-payer",
                merchant_id="m-1",
                amount_minor=25_000,
                fee_minor=250,
                currency="XOF",
                reference="Table 4",
            ),
            MerchantPaymentRefunded(
                occurred_at=T0,
                aggregate_id="pay-1",
                payer_id="u-payer",
                merchant_id="m-1",
                amount_minor=25_000,
                fee_minor=250,
                currency="XOF",
                reference="Table 4",
                reversal_transaction_id="rev-9",
            ),
        ]
    )
    kinds = [n.kind for n in notifier.for_user("u-payer")]
    assert kinds == [NotificationKind.MERCHANT_PAYMENT, NotificationKind.REVERSAL]


def test_kyc_events_notify_user(
    dispatcher: NotificationDispatcher, notifier: RecordingNotifier
) -> None:
    dispatcher.handle(
        [
            KycCaseApproved(
                occurred_at=T0,
                aggregate_id="c-1",
                user_id="u-1",
                target_tier=1,
                reviewer_id="admin",
            ),
            KycCaseRejected(
                occurred_at=T0,
                aggregate_id="c-2",
                user_id="u-2",
                reviewer_id="admin",
                reason="Selfie illisible",
            ),
        ]
    )
    approved = notifier.for_user("u-1")[0]
    assert approved.kind is NotificationKind.KYC and approved.data["target_tier"] == 1
    rejected = notifier.for_user("u-2")[0]
    assert "Selfie illisible" in rejected.body


def test_unmapped_event_produces_nothing(
    dispatcher: NotificationDispatcher, notifier: RecordingNotifier
) -> None:
    dispatcher.handle([DomainEvent(occurred_at=T0, aggregate_id="x")])
    assert notifier.delivered == []
