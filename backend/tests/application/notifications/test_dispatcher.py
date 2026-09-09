"""Tests du NotificationDispatcher : événement de domaine -> notification(s) (BE-040)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from flash.application.notifications.dispatcher import NotificationDispatcher
from flash.application.notifications.model import NotificationKind
from flash.domain.card.events import (
    CardFrozen,
    CardPaymentAuthorized,
    CardPaymentDeclined,
    CardPaymentRefunded,
)
from flash.domain.cash.events import CashDepositCompleted, CashWithdrawalConfirmed
from flash.domain.identity.events import KycCaseApproved, KycCaseRejected
from flash.domain.merchants.events import (
    MerchantPaymentCompleted,
    MerchantPaymentRefunded,
    MerchantSettlementFailed,
    MerchantSettlementPaid,
)
from flash.domain.operators.events import (
    OperatorTransferFailed,
    OperatorTransferSucceeded,
)
from flash.domain.savings.events import (
    SavingsContributionSkipped,
    SavingsInterestCapitalised,
    SavingsPlanClosed,
    SavingsPlanFunded,
)
from flash.domain.shared.events import DomainEvent
from flash.domain.vault.events import VaultPocketDeposited, VaultPocketWithdrawn
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


def test_settlement_events_notify_merchant(
    dispatcher: NotificationDispatcher, notifier: RecordingNotifier
) -> None:
    dispatcher.handle(
        [
            MerchantSettlementPaid(
                occurred_at=T0,
                aggregate_id="set-1",
                user_id="u-merchant",
                merchant_id="m-1",
                amount_minor=24_750,
                currency="XOF",
                bank_reference="bank_ref_001",
            ),
            MerchantSettlementFailed(
                occurred_at=T0,
                aggregate_id="set-2",
                user_id="u-merchant",
                merchant_id="m-1",
                amount_minor=24_750,
                currency="XOF",
                reason="Compte clos",
            ),
        ]
    )
    notes = notifier.for_user("u-merchant")
    assert [n.kind for n in notes] == [
        NotificationKind.SETTLEMENT,
        NotificationKind.SETTLEMENT,
    ]
    assert "bank_ref_001" in notes[0].data["bank_reference"]
    assert "Compte clos" in notes[1].body


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


def test_vault_moves_notify_owner(
    dispatcher: NotificationDispatcher, notifier: RecordingNotifier
) -> None:
    dispatcher.handle(
        [
            VaultPocketDeposited(
                occurred_at=T0,
                aggregate_id="v-1",
                user_id="u-1",
                wallet_id="w-1",
                pocket_id="p-1",
                pocket_name="Vacances",
                amount_minor=20_000,
                currency="XOF",
            ),
            VaultPocketWithdrawn(
                occurred_at=T0,
                aggregate_id="v-1",
                user_id="u-1",
                wallet_id="w-1",
                pocket_id="p-1",
                pocket_name="Vacances",
                amount_minor=5_000,
                currency="XOF",
            ),
        ]
    )
    notes = notifier.for_user("u-1")
    assert [n.kind for n in notes] == [NotificationKind.VAULT, NotificationKind.VAULT]
    assert "20 000 XOF" in notes[0].body and "Vacances" in notes[0].body
    assert notes[1].data["pocket_id"] == "p-1"


def test_savings_events_notify_owner(
    dispatcher: NotificationDispatcher, notifier: RecordingNotifier
) -> None:
    dispatcher.handle(
        [
            SavingsPlanFunded(
                occurred_at=T0,
                aggregate_id="p-1",
                user_id="u-1",
                wallet_id="w-1",
                plan_id="p-1",
                plan_name="Voyage",
                amount_minor=5_000,
                currency="XOF",
                scheduled=True,
            ),
            SavingsPlanFunded(
                occurred_at=T0,
                aggregate_id="p-1",
                user_id="u-1",
                wallet_id="w-1",
                plan_id="p-1",
                plan_name="Voyage",
                amount_minor=9_000,
                currency="XOF",
                scheduled=False,  # versement manuel : pas de notification
            ),
            SavingsContributionSkipped(
                occurred_at=T0,
                aggregate_id="p-1",
                user_id="u-1",
                wallet_id="w-1",
                plan_id="p-1",
                plan_name="Voyage",
                amount_minor=5_000,
                currency="XOF",
            ),
            SavingsInterestCapitalised(
                occurred_at=T0,
                aggregate_id="p-1",
                user_id="u-1",
                wallet_id="w-1",
                plan_id="p-1",
                plan_name="Voyage",
                amount_minor=120,
                currency="XOF",
            ),
            SavingsPlanClosed(
                occurred_at=T0,
                aggregate_id="p-1",
                user_id="u-1",
                wallet_id="w-1",
                plan_id="p-1",
                plan_name="Voyage",
                amount_minor=50_000,
                currency="XOF",
            ),
        ]
    )
    notes = notifier.for_user("u-1")
    assert [n.kind for n in notes] == [NotificationKind.SAVINGS] * 4
    assert "5 000 XOF" in notes[0].body and "Voyage" in notes[0].body
    assert "reporté" in notes[1].body
    assert "intérêts" in notes[2].body.lower()
    assert "clôturé" in notes[3].body


def test_card_events_notify_holder(
    dispatcher: NotificationDispatcher, notifier: RecordingNotifier
) -> None:
    dispatcher.handle(
        [
            CardPaymentAuthorized(
                occurred_at=T0,
                aggregate_id="a-1",
                user_id="u-1",
                wallet_id="w-1",
                card_id="c-1",
                authorization_id="auth-1",
                amount_minor=30_000,
                currency="XOF",
                channel="ECOM",
                merchant_name="Café",
            ),
            CardPaymentDeclined(
                occurred_at=T0,
                aggregate_id="a-2",
                user_id="u-1",
                card_id="c-1",
                authorization_id="auth-2",
                amount_minor=5_000,
                currency="XOF",
                reason="CARD_LIMIT_REACHED",
            ),
            CardFrozen(
                occurred_at=T0, aggregate_id="c-1", user_id="u-1", card_id="c-1", reason="perte"
            ),
            CardPaymentRefunded(
                occurred_at=T0,
                aggregate_id="a-1",
                user_id="u-1",
                wallet_id="w-1",
                card_id="c-1",
                authorization_id="auth-1",
                amount_minor=30_000,
                currency="XOF",
            ),
        ]
    )
    notes = notifier.for_user("u-1")
    assert [n.kind for n in notes] == [NotificationKind.CARD] * 4
    assert "Café" in notes[0].body
    assert "CARD_LIMIT_REACHED" in notes[1].body
    assert "gelée" in notes[2].body
    assert "remboursés" in notes[3].body


def test_operator_events_notify_user(
    dispatcher: NotificationDispatcher, notifier: RecordingNotifier
) -> None:
    dispatcher.handle(
        [
            OperatorTransferSucceeded(
                occurred_at=T0,
                aggregate_id="t-1",
                user_id="u-1",
                wallet_id="w-1",
                operator="ORANGE_CI",
                direction="PAYOUT",
                msisdn_masked="+225070***0304",
                amount_minor=50_000,
                fee_minor=750,
                currency="XOF",
                reference="OPO-1",
            ),
            OperatorTransferSucceeded(
                occurred_at=T0,
                aggregate_id="t-2",
                user_id="u-1",
                wallet_id="w-1",
                operator="MTN_CI",
                direction="COLLECT",
                msisdn_masked="+225050***9999",
                amount_minor=30_000,
                fee_minor=300,
                currency="XOF",
                reference="OPC-1",
            ),
            OperatorTransferFailed(
                occurred_at=T0,
                aggregate_id="t-3",
                user_id="u-1",
                wallet_id="w-1",
                operator="ORANGE_CI",
                direction="PAYOUT",
                amount_minor=50_000,
                currency="XOF",
                reference="OPO-3",
                reason="TIMEOUT",
            ),
        ]
    )
    notes = notifier.for_user("u-1")
    assert [n.kind for n in notes] == [NotificationKind.OPERATOR] * 3
    assert "envoyés" in notes[0].body
    assert "29 700 XOF" in notes[1].body  # net de frais
    assert "échoué" in notes[2].body and "TIMEOUT" in notes[2].body


def test_unmapped_event_produces_nothing(
    dispatcher: NotificationDispatcher, notifier: RecordingNotifier
) -> None:
    dispatcher.handle([DomainEvent(occurred_at=T0, aggregate_id="x")])
    assert notifier.delivered == []
