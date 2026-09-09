"""Tests d'intégration du socle DB : mappers, dépôts, Unit of Work (BE-017 → BE-020).

Nécessite un PostgreSQL réel (``FLASH_TEST_DATABASE_URL``).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from flash.domain.identity.user import User, UserStatus
from flash.domain.ledger.chart import AccountType
from flash.domain.ledger.transaction import LedgerTransaction
from flash.domain.shared.identifiers import CountryCode, EntityId, Msisdn
from flash.domain.shared.money import XOF, Money
from flash.domain.wallet.wallet import Wallet
from flash.infrastructure.db.models import OutboxModel
from flash.infrastructure.db.uow import SqlAlchemyUnitOfWork
from flash.infrastructure.ids import uuid7
from tests.support.fakes import FixedClock

pytestmark = pytest.mark.integration

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _new_user(msisdn: str = "+2250700000001") -> User:
    user = User.register(
        user_id=EntityId(str(uuid7())),
        country=CountryCode("CI"),
        msisdn=Msisdn(msisdn),
        pin_hash="hashed:1397",
        now=T0,
    )
    user.activate(T0)
    return user


class TestUserRepositoryRoundtrip:
    def test_add_get_and_save_user(self, session_factory: sessionmaker[Session]) -> None:
        clock = FixedClock(T0)
        user = _new_user()
        user_id = user.id

        with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
            uow.users.add(user)
            uow.commit()

        with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
            loaded = uow.users.get(user_id)
            assert loaded is not None
            assert loaded.status is UserStatus.ACTIVE
            assert loaded.primary_phone_number.msisdn == Msisdn("+2250700000001")

            loaded.add_phone_number(Msisdn("+2250700000002"), T0)
            uow.users.save(loaded)
            uow.commit()

        with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
            again = uow.users.get(user_id)
            assert again is not None
            assert {p.msisdn.value for p in again.phone_numbers} == {
                "+2250700000001",
                "+2250700000002",
            }

    def test_global_msisdn_uniqueness_enforced(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        from flash.domain.shared.errors import PhoneNumberAlreadyLinked

        clock = FixedClock(T0)
        with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
            uow.users.add(_new_user("+2250700000001"))
            uow.commit()

        clash = _new_user("+2250700000001")
        with (
            SqlAlchemyUnitOfWork(session_factory, clock) as uow,
            pytest.raises(PhoneNumberAlreadyLinked),
        ):
            uow.users.add(clash)


class TestLedgerAndWalletRoundtrip:
    def test_transfer_persists_balanced_transaction_and_updates_wallets(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        clock = FixedClock(T0)
        sender = _new_user("+2250700000001")
        recipient = _new_user("+2250700000002")
        sender_wallet = Wallet.open(
            wallet_id=EntityId(str(uuid7())), user_id=sender.id, currency=XOF, now=T0
        )
        recipient_wallet = Wallet.open(
            wallet_id=EntityId(str(uuid7())), user_id=recipient.id, currency=XOF, now=T0
        )
        sender_wallet.credit(Money(100_000, XOF), T0)

        with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
            uow.users.add(sender)
            uow.users.add(recipient)
            uow.wallets.add(sender_wallet)
            uow.wallets.add(recipient_wallet)

            sender_acct = uow.ledger.ensure_account(
                account_type=AccountType.CLIENT_LIABILITY, currency=XOF, owner_ref=str(sender.id)
            )
            recipient_acct = uow.ledger.ensure_account(
                account_type=AccountType.CLIENT_LIABILITY,
                currency=XOF,
                owner_ref=str(recipient.id),
            )
            fee_acct = uow.ledger.ensure_account(
                account_type=AccountType.FLASH_FEE_INCOME, currency=XOF
            )

            amount, fee = Money(10_000, XOF), Money(80, XOF)
            txn = LedgerTransaction.transfer(
                id=EntityId(str(uuid7())),
                occurred_at=T0,
                reference="TRX-INT-1",
                sender_account_id=sender_acct,
                sender_wallet_id=sender_wallet.id,
                recipient_account_id=recipient_acct,
                recipient_wallet_id=recipient_wallet.id,
                fee_income_account_id=fee_acct,
                amount=amount,
                fee=fee,
            )
            uow.ledger.add(txn)
            sender_wallet.debit(amount + fee, T0)
            recipient_wallet.credit(amount, T0)
            uow.wallets.save(sender_wallet)
            uow.wallets.save(recipient_wallet)
            uow.commit()

        with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
            s = uow.wallets.get_for_user(sender.id, XOF)
            r = uow.wallets.get_for_user(recipient.id, XOF)
            assert s is not None and r is not None
            assert s.available == Money(89_920, XOF)
            assert r.available == Money(10_000, XOF)

            stored = uow.ledger.get_by_reference("TRX-INT-1")
            assert len(stored) == 1
            assert stored[0].is_balanced
            history = uow.ledger.list_for_wallet(sender_wallet.id)
            assert [t.reference for t in history] == ["TRX-INT-1"]

            # BE-077 : list_accounts + list_between alimentent la balance générale
            accounts = {a.type for a in uow.ledger.list_accounts()}
            assert AccountType.CLIENT_LIABILITY in accounts
            assert AccountType.FLASH_FEE_INCOME in accounts
            window = uow.ledger.list_between(
                T0 - timedelta(days=1), T0 + timedelta(days=1)
            )
            assert [t.reference for t in window] == ["TRX-INT-1"]
            assert uow.ledger.list_between(T0 + timedelta(days=1), T0 + timedelta(days=2)) == []

    def test_ensure_account_is_idempotent(self, session_factory: sessionmaker[Session]) -> None:
        clock = FixedClock(T0)
        with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
            a = uow.ledger.ensure_account(account_type=AccountType.ROUNDING, currency=XOF)
            b = uow.ledger.ensure_account(account_type=AccountType.ROUNDING, currency=XOF)
            assert a == b
            uow.commit()


class TestAgentAndCashOrderRoundtrip:
    def test_agent_and_cash_order_persist_and_reload(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        from datetime import timedelta

        from flash.domain.agent.agent import Agent, AgentStatus
        from flash.domain.cash.order import CashOrder, CashOrderStatus

        clock = FixedClock(T0)
        client = _new_user("+2250700000021")
        agent_user = _new_user("+2250700000029")
        agent = Agent.enroll(
            agent_id=EntityId(str(uuid7())),
            user_id=agent_user.id,
            currency=XOF,
            float_cap=Money(1_000_000, XOF),
            commission_bps=100,
            now=T0,
            initial_float=Money(200_000, XOF),
        )
        order = CashOrder.initiate_withdrawal(
            order_id=EntityId(str(uuid7())),
            client_id=client.id,
            amount=Money(30_000, XOF),
            fee=Money(0, XOF),
            code_hash="deadbeef" * 8,
            expires_at=T0 + timedelta(minutes=15),
            now=T0,
        )

        with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
            uow.users.add(client)
            uow.users.add(agent_user)
            uow.commit()

        with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
            uow.agents.add(agent)
            uow.cash_orders.add(order)
            uow.commit()

        with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
            reloaded_agent = uow.agents.get_by_user_id(agent_user.id)
            assert reloaded_agent is not None
            assert reloaded_agent.float_available == Money(200_000, XOF)
            assert reloaded_agent.status is AgentStatus.ACTIVE

            pending = uow.cash_orders.get_pending_withdrawal_by_code_hash("deadbeef" * 8)
            assert pending is not None
            assert pending.status is CashOrderStatus.INITIATED
            assert pending.amount == Money(30_000, XOF)

            reloaded_agent.collect_float(Money(30_000, XOF), T0)
            pending.confirm(
                agent_id=reloaded_agent.id,
                code_matches=True,
                ledger_transaction_id=EntityId(str(uuid7())),
                now=T0,
            )
            uow.agents.save(reloaded_agent)
            uow.cash_orders.save(pending)
            uow.commit()

        with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
            assert uow.cash_orders.get_pending_withdrawal_by_code_hash("deadbeef" * 8) is None
            final_agent = uow.agents.get(agent.id)
            assert final_agent is not None
            assert final_agent.float_available == Money(230_000, XOF)
            assert final_agent.commission_earned == Money(0, XOF)
            assert final_agent.parent_agent_id is None
            [op] = uow.cash_orders.list_for_agent(agent.id)
            assert op.id == order.id

    def test_agent_hierarchy_and_commission_counters_persist(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        from flash.domain.agent.agent import Agent

        clock = FixedClock(T0)
        master_user = _new_user("+2250700000031")
        sub_user = _new_user("+2250700000032")
        master = Agent.enroll(
            agent_id=EntityId(str(uuid7())),
            user_id=master_user.id,
            currency=XOF,
            float_cap=Money(1_000_000, XOF),
            commission_bps=50,
            now=T0,
        )
        sub = Agent.enroll(
            agent_id=EntityId(str(uuid7())),
            user_id=sub_user.id,
            currency=XOF,
            float_cap=Money(1_000_000, XOF),
            commission_bps=100,
            now=T0,
            initial_float=Money(100_000, XOF),
        )
        with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
            uow.users.add(master_user)
            uow.users.add(sub_user)
            uow.commit()
        with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
            uow.agents.add(master)
            uow.agents.add(sub)
            uow.commit()

        with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
            loaded = uow.agents.get(sub.id)
            assert loaded is not None
            loaded.attach_to_master(master.id, T0)
            loaded.accrue_commission(Money(4_000, XOF), T0)
            uow.agents.save(loaded)
            uow.commit()

        with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
            again = uow.agents.get(sub.id)
            assert again is not None
            assert again.parent_agent_id == master.id
            assert again.commission_owed == Money(4_000, XOF)
            owed = uow.agents.list_with_commission_owed(1_000)
            assert [a.id for a in owed] == [sub.id]


class TestKycCaseRoundtrip:
    def test_kyc_case_with_documents_persists_and_reloads(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        from flash.domain.identity.kyc import KycTier
        from flash.domain.identity.kyc_case import (
            KycCase,
            KycCaseStatus,
            KycDocument,
            KycDocumentKind,
        )

        clock = FixedClock(T0)
        user = _new_user("+2250700000031")
        case = KycCase.submit(
            case_id=EntityId(str(uuid7())),
            user_id=user.id,
            target_tier=KycTier.TIER_1,
            documents=[
                KycDocument(
                    kind=KycDocumentKind.ID_FRONT,
                    storage_key="u/c/id-front.jpg",
                    content_type="image/jpeg",
                    byte_size=2048,
                    uploaded_at=T0,
                ),
                KycDocument(
                    kind=KycDocumentKind.SELFIE,
                    storage_key="u/c/selfie.jpg",
                    content_type="image/jpeg",
                    byte_size=4096,
                    uploaded_at=T0,
                ),
            ],
            now=T0,
        )

        with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
            uow.users.add(user)
            uow.commit()

        with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
            uow.kyc_cases.add(case)
            uow.commit()

        with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
            pending = uow.kyc_cases.get_pending_for_user(user.id)
            assert pending is not None
            assert {d.kind for d in pending.documents} == {
                KycDocumentKind.ID_FRONT,
                KycDocumentKind.SELFIE,
            }
            pending.approve(reviewer_id=EntityId(str(uuid7())), now=T0)
            uow.kyc_cases.save(pending)
            uow.commit()

        with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
            assert uow.kyc_cases.get_pending_for_user(user.id) is None
            [only] = uow.kyc_cases.list_for_user(user.id)
            assert only.status is KycCaseStatus.APPROVED
            assert len(only.documents) == 2


class TestPaymentRequestRoundtrip:
    def test_payment_request_persists_and_reloads(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        from datetime import timedelta

        from flash.domain.payments.request import PaymentRequest, PaymentRequestStatus

        clock = FixedClock(T0)
        requester = _new_user("+2250700000041")
        payer = _new_user("+2250700000042")
        request = PaymentRequest.open(
            request_id=EntityId(str(uuid7())),
            requester_id=requester.id,
            payer_id=payer.id,
            amount=Money(15_000, XOF),
            now=T0,
            expires_at=T0 + timedelta(days=7),
            note="Part de course",
        )

        with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
            uow.users.add(requester)
            uow.users.add(payer)
            uow.commit()

        with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
            uow.payment_requests.add(request)
            uow.commit()

        with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
            [incoming] = uow.payment_requests.list_incoming(payer.id)
            assert incoming.status is PaymentRequestStatus.PENDING
            assert incoming.note == "Part de course"
            assert uow.payment_requests.list_outgoing(requester.id)[0].id == request.id

            transfer_id = EntityId(str(uuid7()))
            incoming.accept(transfer_id=transfer_id, now=T0)
            uow.payment_requests.save(incoming)
            uow.commit()

        with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
            reloaded = uow.payment_requests.get(request.id)
            assert reloaded is not None
            assert reloaded.status is PaymentRequestStatus.ACCEPTED
            assert reloaded.resulting_transfer_id is not None


class TestMerchantRoundtrip:
    def test_merchant_charge_and_payment_persist(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        from datetime import timedelta

        from flash.domain.merchants.charge import MerchantCharge, MerchantChargeStatus
        from flash.domain.merchants.merchant import Merchant
        from flash.domain.merchants.payment import MerchantPayment

        clock = FixedClock(T0)
        owner = _new_user("+2250700000051")
        payer = _new_user("+2250700000052")
        merchant = Merchant.enroll(
            merchant_id=EntityId(str(uuid7())),
            user_id=owner.id,
            display_name="Chez Awa",
            category="RESTAURANT",
            currency=XOF,
            fee_bps=100,
            now=T0,
        )
        charge = MerchantCharge.open(
            charge_id=EntityId(str(uuid7())),
            merchant_id=merchant.id,
            amount=Money(25_000, XOF),
            reference="Table 4",
            now=T0,
            expires_at=T0 + timedelta(minutes=60),
        )

        with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
            uow.users.add(owner)
            uow.users.add(payer)
            uow.commit()

        with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
            uow.merchants.add(merchant)
            uow.commit()

        with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
            uow.merchant_charges.add(charge)
            uow.commit()

        txn_id = EntityId(str(uuid7()))
        with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
            reloaded = uow.merchants.get_by_user_id(owner.id)
            assert reloaded is not None
            assert reloaded.fee_for(Money(25_000, XOF)) == Money(250, XOF)

            locked = uow.merchant_charges.get_for_update(charge.id)
            locked.ensure_payable(T0)
            locked.mark_paid(payer_id=payer.id, ledger_transaction_id=txn_id)
            uow.merchant_charges.save(locked)

            payment = MerchantPayment.record(
                payment_id=EntityId(str(uuid7())),
                payer_id=payer.id,
                merchant_id=merchant.id,
                amount=Money(25_000, XOF),
                fee=Money(250, XOF),
                reference="Table 4",
                ledger_transaction_id=txn_id,
                now=T0,
                charge_id=charge.id,
            )
            uow.merchant_payments.add(payment)
            uow.commit()

        with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
            again = uow.merchant_charges.get(charge.id)
            assert again is not None and again.status is MerchantChargeStatus.PAID
            [p] = uow.merchant_payments.list_for_merchant(merchant.id)
            assert p.net_to_merchant == Money(24_750, XOF)
            assert uow.merchant_payments.get_by_ledger_transaction_id(txn_id) is not None


    def test_merchant_kyb_and_api_key_persist(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        from flash.domain.merchants.api_key import MerchantApiKey
        from flash.domain.merchants.merchant import KybStatus, Merchant

        clock = FixedClock(T0)
        owner = _new_user("+2250700000061")
        merchant = Merchant.enroll(
            merchant_id=EntityId(str(uuid7())),
            user_id=owner.id,
            display_name="Chez Awa",
            category="RESTAURANT",
            currency=XOF,
            fee_bps=100,
            now=T0,
        )
        with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
            uow.users.add(owner)
            uow.merchants.add(merchant)
            uow.commit()

        key_id = EntityId(str(uuid7()))
        with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
            loaded = uow.merchants.get(merchant.id)
            assert loaded is not None and loaded.kyb_status is KybStatus.PENDING
            loaded.approve_kyb(reviewer="key:compliance", now=T0)
            uow.merchants.save(loaded)
            uow.merchant_api_keys.add(
                MerchantApiKey.issue(
                    key_id=key_id,
                    merchant_id=merchant.id,
                    prefix="abcd1234",
                    secret_hash="f" * 64,
                    label="Caisse",
                    now=T0,
                )
            )
            uow.commit()

        with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
            again = uow.merchants.get(merchant.id)
            assert again is not None and again.kyb_status is KybStatus.APPROVED
            assert again.kyb_reviewed_at is not None
            by_prefix = uow.merchant_api_keys.get_by_prefix("abcd1234")
            assert by_prefix is not None and by_prefix.id == key_id
            [listed] = uow.merchant_api_keys.list_for_merchant(merchant.id)
            listed.revoke(T0)
            uow.merchant_api_keys.save(listed)
            uow.commit()

        with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
            revoked = uow.merchant_api_keys.get(key_id)
            assert revoked is not None and revoked.is_active is False

    def test_merchant_webhook_config_and_delivery_persist(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        from flash.domain.merchants.merchant import Merchant
        from flash.domain.merchants.webhook import (
            MerchantWebhookDelivery,
            MerchantWebhookStatus,
        )

        clock = FixedClock(T0)
        owner = _new_user("+2250700000062")
        merchant = Merchant.enroll(
            merchant_id=EntityId(str(uuid7())),
            user_id=owner.id,
            display_name="Chez Awa",
            category="RESTAURANT",
            currency=XOF,
            fee_bps=100,
            now=T0,
        )
        merchant.configure_webhook(
            url="https://shop.example.com/hook",
            secret="merchant-webhook-secret-32chars!!",
            now=T0,
        )
        source_id = EntityId(str(uuid7()))
        delivery = MerchantWebhookDelivery.enqueue(
            delivery_id=EntityId(str(uuid7())),
            merchant_id=merchant.id,
            source_id=source_id,
            event_type="payment.completed",
            payload={"type": "payment.completed", "data": {"amount_minor": 25_000}},
            now=T0,
        )
        with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
            uow.users.add(owner)
            uow.merchants.add(merchant)
            uow.merchant_webhooks.add(delivery)
            uow.commit()

        with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
            again = uow.merchants.get(merchant.id)
            assert again is not None and again.has_webhook
            assert again.webhook_url == "https://shop.example.com/hook"
            assert uow.merchant_webhooks.exists_for_source("payment.completed", source_id)
            [due] = uow.merchant_webhooks.list_due(T0)
            due.record_success(T0)
            uow.merchant_webhooks.save(due)
            uow.commit()

        with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
            settled = uow.merchant_webhooks.get(delivery.id)
            assert settled is not None
            assert settled.status is MerchantWebhookStatus.DELIVERED
            assert uow.merchant_webhooks.list_due(T0) == []


class TestComplianceRoundtrip:
    def test_compliance_alert_persists_and_dedups(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        from flash.domain.compliance.alert import AlertKind, AlertStatus, ComplianceAlert

        clock = FixedClock(T0)
        user = _new_user("+2250700000081")
        alert = ComplianceAlert.open(
            alert_id=EntityId(str(uuid7())),
            user_id=user.id,
            kind=AlertKind.VELOCITY,
            score=70,
            detail={"count": 22, "volume_minor": 4_000_000},
            window_key="vel:2026-01-01",
            now=T0,
        )
        with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
            uow.users.add(user)
            uow.compliance_alerts.add(alert)
            uow.commit()

        with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
            assert uow.compliance_alerts.exists_window(
                user.id, "VELOCITY", "vel:2026-01-01"
            )
            [loaded] = uow.compliance_alerts.list_open()
            assert loaded.detail["count"] == 22
            loaded.escalate(analyst="key:compliance", note="STR", now=T0)
            uow.compliance_alerts.save(loaded)
            uow.commit()

        with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
            assert uow.compliance_alerts.list_open() == []
            [escalated] = uow.compliance_alerts.list_by_status("ESCALATED")
            assert escalated.status is AlertStatus.ESCALATED
            window = uow.compliance_alerts.list_between(
                "2025-12-01T00:00:00+00:00", "2026-12-01T00:00:00+00:00"
            )
            assert [a.id for a in window] == [alert.id]


class TestBackofficeRoundtrip:
    def test_support_notes_and_tickets_persist(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        from flash.domain.support.ticket import SupportNote, SupportTicket, TicketStatus

        clock = FixedClock(T0)
        user = _new_user("+2250700000071")
        note = SupportNote(
            id=EntityId(str(uuid7())),
            subject_user_id=user.id,
            author="key:support",
            body="Client rappelé",
            created_at=T0,
        )
        ticket = SupportTicket.open(
            ticket_id=EntityId(str(uuid7())),
            subject_user_id=user.id,
            opened_by="key:support",
            subject="Retrait bloqué",
            now=T0,
        )
        with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
            uow.users.add(user)
            uow.support_notes.add(note)
            uow.support_tickets.add(ticket)
            uow.commit()

        with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
            [loaded_note] = uow.support_notes.list_for_user(user.id)
            assert loaded_note.body == "Client rappelé"
            loaded_ticket = uow.support_tickets.get(ticket.id)
            assert loaded_ticket is not None
            loaded_ticket.transition_to(
                TicketStatus.RESOLVED, actor="key:compliance", now=T0
            )
            uow.support_tickets.save(loaded_ticket)
            uow.commit()

        with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
            [resolved] = uow.support_tickets.list_recent(status="RESOLVED")
            assert resolved.id == ticket.id
            assert resolved.last_actor == "key:compliance"
            assert uow.support_tickets.list_recent(status="OPEN") == []
            assert [t.id for t in uow.support_tickets.list_for_user(user.id)] == [ticket.id]


class TestNotificationRepository:
    def test_add_list_count_and_mark_read(self, session_factory: sessionmaker[Session]) -> None:
        from flash.application.notifications.model import Notification, NotificationKind
        from flash.infrastructure.db.notification_repository import (
            SqlAlchemyNotificationRepository,
        )

        clock = FixedClock(T0)
        user = _new_user("+2250700000061")
        with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
            uow.users.add(user)
            uow.commit()

        repo = SqlAlchemyNotificationRepository(session_factory)
        for i in range(3):
            repo.add(
                Notification(
                    id=str(uuid7()),
                    user_id=str(user.id),
                    kind=NotificationKind.MONEY_IN,
                    title=f"n{i}",
                    body="Vous avez reçu de l'argent.",
                    created_at=T0,
                    data={"reference": f"TRX-{i}"},
                )
            )
        listed = repo.list_for_user(str(user.id), limit=2)
        assert len(listed) == 2
        assert listed[0].data["reference"].startswith("TRX-")
        assert repo.count_unread(str(user.id)) == 3

        assert repo.mark_read(str(user.id), listed[0].id) is True
        assert repo.mark_read(str(user.id), listed[0].id) is False  # déjà lue
        assert repo.count_unread(str(user.id)) == 2

        assert repo.mark_all_read(str(user.id)) == 2
        assert repo.count_unread(str(user.id)) == 0
        assert repo.list_for_user(str(user.id), unread_only=True) == []


class TestUnitOfWork:
    def test_commit_writes_domain_events_to_outbox(
        self, session_factory: sessionmaker[Session], db_session: Session
    ) -> None:
        clock = FixedClock(T0)
        with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
            uow.users.add(_new_user("+2250700000009"))
            uow.commit()
            collected = uow.collect_new_events()

        assert {e.name for e in collected} >= {"UserRegistered", "PhoneNumberVerified"}
        names = db_session.scalars(select(OutboxModel.event_name)).all()
        assert "UserRegistered" in names
        assert db_session.scalar(select(func.count()).select_from(OutboxModel)) == len(collected)

    def test_exception_in_block_rolls_back(
        self, session_factory: sessionmaker[Session], db_session: Session
    ) -> None:
        clock = FixedClock(T0)
        with (
            pytest.raises(RuntimeError, match="boom"),
            SqlAlchemyUnitOfWork(session_factory, clock) as uow,
        ):
            uow.users.add(_new_user("+2250700000010"))
            raise RuntimeError("boom")

        from flash.infrastructure.db.models import UserModel

        assert db_session.scalar(select(func.count()).select_from(UserModel)) == 0
