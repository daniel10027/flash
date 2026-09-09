"""Cas d'usage back-office (BE-075) : recherche, détail, gel, transactions, reversal
forcé, notes, tickets. Chaque action doit tracer une entrée d'audit."""

from __future__ import annotations

from uuid import UUID

import pytest

from flash.application.backoffice.operations import (
    AddAccountNote,
    AddAccountNoteCommand,
    ForceTransferReversal,
    ForceTransferReversalCommand,
    GetAccountDetail,
    GetAccountDetailCommand,
    ListAccountNotes,
    ListAccountNotesCommand,
    ListAccountTransactions,
    ListAccountTransactionsCommand,
    ListSupportTickets,
    ListSupportTicketsCommand,
    OpenSupportTicket,
    OpenSupportTicketCommand,
    SearchAccount,
    SearchAccountCommand,
    SetAccountFrozen,
    SetAccountFrozenCommand,
    SetTicketStatus,
    SetTicketStatusCommand,
)
from flash.application.services import AppServices
from flash.domain.identity.pin import Pin
from flash.domain.identity.user import User, UserStatus
from flash.domain.ledger.transaction import LedgerTransaction
from flash.domain.shared.errors import DuplicateOperation, InsufficientFunds, InvalidInput
from flash.domain.shared.identifiers import CountryCode, EntityId, Msisdn
from flash.domain.shared.money import XOF, Money
from flash.domain.wallet.wallet import Wallet
from tests.support.audit import InMemoryAuditLog
from tests.support.fakes import (
    FakePinHasher,
    FixedClock,
    InMemoryIdempotencyStore,
    RecordingEventPublisher,
    SeqIdGenerator,
)
from tests.support.repositories import InMemoryUnitOfWork

CI = CountryCode("CI")


@pytest.fixture
def uow() -> InMemoryUnitOfWork:
    return InMemoryUnitOfWork()


@pytest.fixture
def audit() -> InMemoryAuditLog:
    return InMemoryAuditLog()


@pytest.fixture
def services(uow: InMemoryUnitOfWork) -> AppServices:
    return AppServices(
        uow=lambda: uow,
        clock=FixedClock(),
        ids=SeqIdGenerator(),
        events=RecordingEventPublisher(),
        idempotency=InMemoryIdempotencyStore(),
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
        wallet_id=EntityId(str(UUID(int=500 + n))),
        user_id=user.id,
        currency=XOF,
        now=FixedClock().now(),
    )
    if balance:
        wallet.credit(Money(balance, XOF), FixedClock().now())
    wallet.pull_events()
    uow.wallets.add(wallet)
    return user


class TestSearchAndDetail:
    def test_search_by_msisdn_then_by_id(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        user = _user(uow, n=1, msisdn="+2250700000001")
        by_phone = SearchAccount(services=services).execute(
            SearchAccountCommand(query="+2250700000001")
        )
        assert by_phone.user_id == str(user.id)
        by_id = SearchAccount(services=services).execute(
            SearchAccountCommand(query=str(user.id))
        )
        assert by_id.user_id == str(user.id)
        assert by_id.msisdns_masked and "+2250700000001" not in by_id.msisdns_masked[0]

    def test_search_empty_or_unknown_rejected(self, services: AppServices) -> None:
        with pytest.raises(InvalidInput, match="vide"):
            SearchAccount(services=services).execute(SearchAccountCommand(query="  "))
        with pytest.raises(InvalidInput, match="Aucun compte"):
            SearchAccount(services=services).execute(
                SearchAccountCommand(query="+2250799999999")
            )

    def test_search_garbage_rejected(self, services: AppServices) -> None:
        with pytest.raises(InvalidInput, match="identifiant compte"):
            SearchAccount(services=services).execute(SearchAccountCommand(query="???"))

    def test_detail_lists_wallets_notes_tickets(
        self, services: AppServices, uow: InMemoryUnitOfWork, audit: InMemoryAuditLog
    ) -> None:
        user = _user(uow, n=1, msisdn="+2250700000001", balance=50_000)
        AddAccountNote(services=services, audit=audit, clock=FixedClock()).execute(
            AddAccountNoteCommand(
                user_id=str(user.id), body="RAS", author="key:support", role="support"
            )
        )
        OpenSupportTicket(services=services, audit=audit, clock=FixedClock()).execute(
            OpenSupportTicketCommand(
                user_id=str(user.id), subject="Litige", actor="key:support", role="support"
            )
        )
        detail = GetAccountDetail(services=services).execute(
            GetAccountDetailCommand(user_id=str(user.id))
        )
        assert detail.account.status == "ACTIVE"
        assert detail.wallets[0].balance_minor == 50_000
        assert detail.notes_count == 1 and detail.open_tickets == 1
        assert detail.to_dict()["account"]["user_id"] == str(user.id)

    def test_detail_unknown_rejected(self, services: AppServices) -> None:
        with pytest.raises(InvalidInput, match="introuvable"):
            GetAccountDetail(services=services).execute(
                GetAccountDetailCommand(user_id=str(UUID(int=404)))
            )
        with pytest.raises(InvalidInput, match="introuvable"):
            GetAccountDetail(services=services).execute(
                GetAccountDetailCommand(user_id="bad")
            )


class TestFreeze:
    def test_freeze_requires_reason_then_audits(
        self, services: AppServices, uow: InMemoryUnitOfWork, audit: InMemoryAuditLog
    ) -> None:
        user = _user(uow, n=1, msisdn="+2250700000001")
        with pytest.raises(InvalidInput, match="motif"):
            SetAccountFrozen(services=services, audit=audit, clock=FixedClock()).execute(
                SetAccountFrozenCommand(
                    user_id=str(user.id), frozen=True, reason="", actor="key:support",
                    role="support",
                )
            )
        view = SetAccountFrozen(services=services, audit=audit, clock=FixedClock()).execute(
            SetAccountFrozenCommand(
                user_id=str(user.id), frozen=True, reason="fraude", actor="key:support",
                role="support",
            )
        )
        assert view.status == "FROZEN"
        assert uow.users.get(user.id).status is UserStatus.FROZEN  # type: ignore[union-attr]
        assert audit.recent()[0].action == "account.freeze"

    def test_unfreeze(
        self, services: AppServices, uow: InMemoryUnitOfWork, audit: InMemoryAuditLog
    ) -> None:
        user = _user(uow, n=1, msisdn="+2250700000001")
        user.freeze("x", FixedClock().now())
        user.pull_events()
        uow.users.save(user)
        view = SetAccountFrozen(services=services, audit=audit, clock=FixedClock()).execute(
            SetAccountFrozenCommand(
                user_id=str(user.id), frozen=False, reason="", actor="key:support",
                role="support",
            )
        )
        assert view.status == "ACTIVE"
        assert audit.recent()[0].action == "account.unfreeze"

    def test_unknown_account_rejected(
        self, services: AppServices, audit: InMemoryAuditLog
    ) -> None:
        with pytest.raises(InvalidInput, match="introuvable"):
            SetAccountFrozen(services=services, audit=audit, clock=FixedClock()).execute(
                SetAccountFrozenCommand(
                    user_id="bad", frozen=True, reason="x", actor="a", role="support"
                )
            )
        with pytest.raises(InvalidInput, match="introuvable"):
            SetAccountFrozen(services=services, audit=audit, clock=FixedClock()).execute(
                SetAccountFrozenCommand(
                    user_id=str(UUID(int=404)), frozen=True, reason="x", actor="a",
                    role="support",
                )
            )


class TestTransactionsAndReversal:
    def _transfer(
        self, uow: InMemoryUnitOfWork, sender: User, recipient: User, amount: int, fee: int
    ) -> EntityId:
        sender_wallet = uow.wallets.list_for_user(sender.id)[0]
        recipient_wallet = uow.wallets.list_for_user(recipient.id)[0]
        txn_id = EntityId(str(UUID(int=900)))
        uow.ledger.add(
            LedgerTransaction.transfer(
                id=txn_id,
                occurred_at=FixedClock().now(),
                reference="TRX-1",
                sender_account_id=EntityId(str(UUID(int=1001))),
                sender_wallet_id=sender_wallet.id,
                recipient_account_id=EntityId(str(UUID(int=1002))),
                recipient_wallet_id=recipient_wallet.id,
                fee_income_account_id=EntityId(str(UUID(int=1003))),
                amount=Money(amount, XOF),
                fee=Money(fee, XOF),
            )
        )
        sender_wallet.debit(Money(amount + fee, XOF), FixedClock().now())
        recipient_wallet.credit(Money(amount, XOF), FixedClock().now())
        sender_wallet.pull_events()
        recipient_wallet.pull_events()
        uow.wallets.save(sender_wallet)
        uow.wallets.save(recipient_wallet)
        return txn_id

    def test_list_transactions_signed(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        sender = _user(uow, n=1, msisdn="+2250700000001", balance=100_000)
        recipient = _user(uow, n=2, msisdn="+2250700000002")
        self._transfer(uow, sender, recipient, 20_000, 160)
        lines = ListAccountTransactions(services=services).execute(
            ListAccountTransactionsCommand(user_id=str(sender.id))
        )
        assert lines[0].signed_minor == -(20_000 + 160)
        assert lines[0].to_dict()["kind"] == "TRANSFER"

    def test_list_transactions_empty_and_bad_id(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        user = _user(uow, n=1, msisdn="+2250700000001")
        assert (
            ListAccountTransactions(services=services).execute(
                ListAccountTransactionsCommand(user_id=str(user.id))
            )
            == []
        )
        with pytest.raises(InvalidInput, match="introuvable"):
            ListAccountTransactions(services=services).execute(
                ListAccountTransactionsCommand(user_id="bad")
            )

    def test_list_transactions_no_wallet_returns_empty(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        walletless = User.register(
            user_id=EntityId(str(UUID(int=77))),
            country=CI,
            msisdn=Msisdn("+2250700000077"),
            pin_hash=FakePinHasher().hash(Pin("1397")),
            now=FixedClock().now(),
        )
        walletless.pull_events()
        uow.users.add(walletless)
        assert (
            ListAccountTransactions(services=services).execute(
                ListAccountTransactionsCommand(user_id=str(walletless.id))
            )
            == []
        )

    def test_force_reversal_restores_balances_and_audits(
        self, services: AppServices, uow: InMemoryUnitOfWork, audit: InMemoryAuditLog
    ) -> None:
        sender = _user(uow, n=1, msisdn="+2250700000001", balance=100_000)
        recipient = _user(uow, n=2, msisdn="+2250700000002")
        txn_id = self._transfer(uow, sender, recipient, 20_000, 160)

        receipt = ForceTransferReversal(
            services=services, audit=audit, clock=FixedClock()
        ).execute(
            ForceTransferReversalCommand(
                transaction_id=str(txn_id), reason="erreur agent", actor="key:finance",
                role="finance",
            )
        )
        assert receipt.amount_minor == 20_000
        assert receipt.to_dict()["reference"] == "TRX-1"
        assert uow.wallets.list_for_user(sender.id)[0].available == Money(100_000, XOF)
        assert uow.wallets.list_for_user(recipient.id)[0].available == Money(0, XOF)
        assert audit.recent()[0].action == "transaction.force_reversal"

    def test_force_reversal_twice_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork, audit: InMemoryAuditLog
    ) -> None:
        sender = _user(uow, n=1, msisdn="+2250700000001", balance=100_000)
        recipient = _user(uow, n=2, msisdn="+2250700000002")
        txn_id = self._transfer(uow, sender, recipient, 20_000, 0)
        cmd = ForceTransferReversalCommand(
            transaction_id=str(txn_id), reason="x", actor="a", role="finance"
        )
        ForceTransferReversal(services=services, audit=audit, clock=FixedClock()).execute(cmd)
        with pytest.raises(DuplicateOperation):
            ForceTransferReversal(
                services=services, audit=audit, clock=FixedClock()
            ).execute(cmd)

    def test_force_reversal_fails_when_recipient_spent(
        self, services: AppServices, uow: InMemoryUnitOfWork, audit: InMemoryAuditLog
    ) -> None:
        sender = _user(uow, n=1, msisdn="+2250700000001", balance=100_000)
        recipient = _user(uow, n=2, msisdn="+2250700000002")
        txn_id = self._transfer(uow, sender, recipient, 20_000, 0)
        rw = uow.wallets.list_for_user(recipient.id)[0]
        rw.debit(Money(20_000, XOF), FixedClock().now())
        rw.pull_events()
        uow.wallets.save(rw)
        with pytest.raises(InsufficientFunds):
            ForceTransferReversal(
                services=services, audit=audit, clock=FixedClock()
            ).execute(
                ForceTransferReversalCommand(
                    transaction_id=str(txn_id), reason="x", actor="a", role="finance"
                )
            )

    def test_force_reversal_guards(
        self, services: AppServices, uow: InMemoryUnitOfWork, audit: InMemoryAuditLog
    ) -> None:
        with pytest.raises(InvalidInput, match="motif"):
            ForceTransferReversal(
                services=services, audit=audit, clock=FixedClock()
            ).execute(
                ForceTransferReversalCommand(
                    transaction_id=str(UUID(int=1)), reason=" ", actor="a", role="finance"
                )
            )
        with pytest.raises(InvalidInput, match="introuvable"):
            ForceTransferReversal(
                services=services, audit=audit, clock=FixedClock()
            ).execute(
                ForceTransferReversalCommand(
                    transaction_id="bad", reason="x", actor="a", role="finance"
                )
            )
        with pytest.raises(InvalidInput, match="introuvable"):
            ForceTransferReversal(
                services=services, audit=audit, clock=FixedClock()
            ).execute(
                ForceTransferReversalCommand(
                    transaction_id=str(UUID(int=404)), reason="x", actor="a", role="finance"
                )
            )

    def test_force_reversal_rejects_non_transfer(
        self, services: AppServices, uow: InMemoryUnitOfWork, audit: InMemoryAuditLog
    ) -> None:
        _user(uow, n=1, msisdn="+2250700000001")
        txn_id = EntityId(str(UUID(int=950)))
        uow.ledger.add(
            LedgerTransaction.agent_float_topup(
                id=txn_id,
                occurred_at=FixedClock().now(),
                reference="AFT-1",
                bank_settlement_account_id=EntityId(str(UUID(int=1))),
                agent_float_account_id=EntityId(str(UUID(int=2))),
                amount=Money(1_000, XOF),
            )
        )
        with pytest.raises(InvalidInput, match="virements P2P"):
            ForceTransferReversal(
                services=services, audit=audit, clock=FixedClock()
            ).execute(
                ForceTransferReversalCommand(
                    transaction_id=str(txn_id), reason="x", actor="a", role="finance"
                )
            )


class TestNotesAndTickets:
    def test_add_and_list_notes(
        self, services: AppServices, uow: InMemoryUnitOfWork, audit: InMemoryAuditLog
    ) -> None:
        user = _user(uow, n=1, msisdn="+2250700000001")
        view = AddAccountNote(services=services, audit=audit, clock=FixedClock()).execute(
            AddAccountNoteCommand(
                user_id=str(user.id), body="Appel client 14h", author="key:support",
                role="support",
            )
        )
        assert view.body == "Appel client 14h"
        assert view.to_dict()["author"] == "key:support"
        assert audit.recent()[0].action == "account.note"
        notes = ListAccountNotes(services=services).execute(
            ListAccountNotesCommand(user_id=str(user.id))
        )
        assert [n.note_id for n in notes] == [view.note_id]

    def test_note_unknown_account_rejected(
        self, services: AppServices, audit: InMemoryAuditLog
    ) -> None:
        with pytest.raises(InvalidInput, match="introuvable"):
            AddAccountNote(services=services, audit=audit, clock=FixedClock()).execute(
                AddAccountNoteCommand(
                    user_id="bad", body="x", author="a", role="support"
                )
            )
        with pytest.raises(InvalidInput, match="introuvable"):
            AddAccountNote(services=services, audit=audit, clock=FixedClock()).execute(
                AddAccountNoteCommand(
                    user_id=str(UUID(int=404)), body="x", author="a", role="support"
                )
            )

    def test_list_notes_bad_id(self, services: AppServices) -> None:
        with pytest.raises(InvalidInput, match="introuvable"):
            ListAccountNotes(services=services).execute(
                ListAccountNotesCommand(user_id="bad")
            )

    def test_ticket_lifecycle(
        self, services: AppServices, uow: InMemoryUnitOfWork, audit: InMemoryAuditLog
    ) -> None:
        user = _user(uow, n=1, msisdn="+2250700000001")
        ticket = OpenSupportTicket(
            services=services, audit=audit, clock=FixedClock()
        ).execute(
            OpenSupportTicketCommand(
                user_id=str(user.id), subject="Litige retrait", actor="key:support",
                role="support",
            )
        )
        assert ticket.status == "OPEN"
        assert audit.recent()[0].action == "ticket.open"

        moved = SetTicketStatus(
            services=services, audit=audit, clock=FixedClock()
        ).execute(
            SetTicketStatusCommand(
                ticket_id=ticket.ticket_id, status="RESOLVED", actor="key:compliance",
                role="compliance",
            )
        )
        assert moved.status == "RESOLVED" and moved.last_actor == "key:compliance"

        listed = ListSupportTickets(services=services).execute(
            ListSupportTicketsCommand(status="RESOLVED")
        )
        assert [t.ticket_id for t in listed] == [ticket.ticket_id]
        assert listed[0].to_dict()["status"] == "RESOLVED"
        assert ListSupportTickets(services=services).execute(
            ListSupportTicketsCommand(status="OPEN")
        ) == []
        all_tickets = ListSupportTickets(services=services).execute(
            ListSupportTicketsCommand()
        )
        assert [t.ticket_id for t in all_tickets] == [ticket.ticket_id]

    def test_ticket_guards(
        self, services: AppServices, uow: InMemoryUnitOfWork, audit: InMemoryAuditLog
    ) -> None:
        with pytest.raises(InvalidInput, match="introuvable"):
            OpenSupportTicket(
                services=services, audit=audit, clock=FixedClock()
            ).execute(
                OpenSupportTicketCommand(
                    user_id="bad", subject="x", actor="a", role="support"
                )
            )
        with pytest.raises(InvalidInput, match="introuvable"):
            OpenSupportTicket(
                services=services, audit=audit, clock=FixedClock()
            ).execute(
                OpenSupportTicketCommand(
                    user_id=str(UUID(int=404)), subject="x", actor="a", role="support"
                )
            )
        with pytest.raises(InvalidInput, match="inconnu"):
            SetTicketStatus(services=services, audit=audit, clock=FixedClock()).execute(
                SetTicketStatusCommand(
                    ticket_id=str(UUID(int=1)), status="NOPE", actor="a", role="support"
                )
            )
        with pytest.raises(InvalidInput, match="introuvable"):
            SetTicketStatus(services=services, audit=audit, clock=FixedClock()).execute(
                SetTicketStatusCommand(
                    ticket_id="bad", status="OPEN", actor="a", role="support"
                )
            )
        with pytest.raises(InvalidInput, match="introuvable"):
            SetTicketStatus(services=services, audit=audit, clock=FixedClock()).execute(
                SetTicketStatusCommand(
                    ticket_id=str(UUID(int=404)), status="OPEN", actor="a", role="support"
                )
            )
        with pytest.raises(InvalidInput, match="inconnu"):
            ListSupportTickets(services=services).execute(
                ListSupportTicketsCommand(status="NOPE")
            )
