"""Back-office : recherche & détail de compte, gel/dégel, transactions, reversal forcé,
notes et tickets de support (BE-075).

Chaque **action** (gel, dégel, reversal forcé, note, ticket) écrit une entrée dans le
registre d'audit chaîné (``AuditLog``) — qui / quel rôle / quoi / quand / avant → après.
Les lectures ne sont pas auditées.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from flash.application.services import AppServices
from flash.application.transaction import execute_in_uow
from flash.application.unit_of_work import WorkUnitOfWork
from flash.application.use_case import Command, UseCase
from flash.domain.audit.ports import AuditLog
from flash.domain.ledger.chart import Direction
from flash.domain.ledger.transaction import LedgerTransaction, TransactionKind
from flash.domain.shared.errors import DuplicateOperation, InvalidInput
from flash.domain.shared.identifiers import EntityId, Msisdn
from flash.domain.shared.ports import Clock
from flash.domain.support.ticket import SupportNote, SupportTicket, TicketStatus


# ------------------------------------------------------------------ helpers
def _resolve_user_id(uow: WorkUnitOfWork, query: str) -> EntityId:
    raw = query.strip()
    if not raw:
        raise InvalidInput("Requête vide.")
    try:
        return EntityId(raw)
    except ValueError:
        pass
    try:
        msisdn = Msisdn.parse(raw)
    except ValueError as exc:
        raise InvalidInput("Fournir un identifiant compte ou un numéro E.164.") from exc
    user = uow.users.get_by_msisdn(msisdn)
    if user is None:
        raise InvalidInput("Aucun compte pour ce critère.")
    return user.id


# ------------------------------------------------------------------ vues
@dataclass(frozen=True, slots=True)
class AccountSummary:
    user_id: str
    status: str
    kyc_tier: int
    country: str
    msisdns_masked: list[str]
    is_agent: bool
    is_merchant: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "status": self.status,
            "kyc_tier": self.kyc_tier,
            "country": self.country,
            "msisdns_masked": self.msisdns_masked,
            "is_agent": self.is_agent,
            "is_merchant": self.is_merchant,
        }


@dataclass(frozen=True, slots=True)
class WalletLine:
    wallet_id: str
    currency: str
    status: str
    available_minor: int
    balance_minor: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "wallet_id": self.wallet_id,
            "currency": self.currency,
            "status": self.status,
            "available_minor": self.available_minor,
            "balance_minor": self.balance_minor,
        }


@dataclass(frozen=True, slots=True)
class AccountDetail:
    account: AccountSummary
    wallets: list[WalletLine]
    notes_count: int
    open_tickets: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "account": self.account.to_dict(),
            "wallets": [w.to_dict() for w in self.wallets],
            "notes_count": self.notes_count,
            "open_tickets": self.open_tickets,
        }


@dataclass(frozen=True, slots=True)
class LedgerLine:
    transaction_id: str
    kind: str
    reference: str
    occurred_at: str
    signed_minor: int
    currency: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "transaction_id": self.transaction_id,
            "kind": self.kind,
            "reference": self.reference,
            "occurred_at": self.occurred_at,
            "signed_minor": self.signed_minor,
            "currency": self.currency,
        }


def _summary(uow: WorkUnitOfWork, user_id: EntityId) -> AccountSummary:
    user = uow.users.get(user_id)
    if user is None:
        raise InvalidInput("Compte introuvable.")
    return AccountSummary(
        user_id=str(user.id),
        status=user.status.value,
        kyc_tier=int(user.kyc_tier),
        country=user.country.value,
        msisdns_masked=sorted(m.masked() for m in user.msisdns),
        is_agent=uow.agents.get_by_user_id(user.id) is not None,
        is_merchant=uow.merchants.get_by_user_id(user.id) is not None,
    )


# ------------------------------------------------------------------ lectures
@dataclass(frozen=True, slots=True)
class SearchAccountCommand(Command):
    query: str


class SearchAccount(UseCase[SearchAccountCommand, AccountSummary]):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self, command: SearchAccountCommand) -> AccountSummary:
        with self._services.uow() as uow:
            return _summary(uow, _resolve_user_id(uow, command.query))


@dataclass(frozen=True, slots=True)
class GetAccountDetailCommand(Command):
    user_id: str


class GetAccountDetail(UseCase[GetAccountDetailCommand, AccountDetail]):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self, command: GetAccountDetailCommand) -> AccountDetail:
        with self._services.uow() as uow:
            try:
                user_id = EntityId(command.user_id)
            except ValueError as exc:
                raise InvalidInput("Compte introuvable.") from exc
            summary = _summary(uow, user_id)
            wallets = [
                WalletLine(
                    wallet_id=str(w.id),
                    currency=w.currency.code,
                    status=w.status.value,
                    available_minor=w.available.amount_minor,
                    balance_minor=w.balance.amount_minor,
                )
                for w in uow.wallets.list_for_user(user_id)
            ]
            notes = uow.support_notes.list_for_user(user_id)
            tickets = uow.support_tickets.list_for_user(user_id)
            return AccountDetail(
                account=summary,
                wallets=wallets,
                notes_count=len(notes),
                open_tickets=sum(1 for t in tickets if not t.status.is_terminal),
            )


@dataclass(frozen=True, slots=True)
class ListAccountTransactionsCommand(Command):
    user_id: str
    limit: int = 50


class ListAccountTransactions(
    UseCase[ListAccountTransactionsCommand, list[LedgerLine]]
):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(
        self, command: ListAccountTransactionsCommand
    ) -> list[LedgerLine]:
        limit = max(1, min(command.limit, 200))
        with self._services.uow() as uow:
            try:
                user_id = EntityId(command.user_id)
            except ValueError as exc:
                raise InvalidInput("Compte introuvable.") from exc
            wallet_ids = [EntityId(str(w.id)) for w in uow.wallets.list_for_user(user_id)]
            if not wallet_ids:
                return []
            wanted = {str(w) for w in wallet_ids}
            lines: list[LedgerLine] = []
            for txn in uow.ledger.list_for_wallets(wallet_ids, limit=limit):
                signed = 0
                currency = ""
                for p in txn.postings:
                    if p.wallet_id is not None and str(p.wallet_id) in wanted:
                        currency = p.amount.currency.code
                        signed += (
                            p.amount.amount_minor
                            if p.direction is Direction.CREDIT
                            else -p.amount.amount_minor
                        )
                lines.append(
                    LedgerLine(
                        transaction_id=str(txn.id),
                        kind=txn.kind.value,
                        reference=txn.reference,
                        occurred_at=txn.occurred_at.isoformat(),
                        signed_minor=signed,
                        currency=currency,
                    )
                )
            return lines


# ------------------------------------------------------------------ actions
@dataclass(frozen=True, slots=True)
class SetAccountFrozenCommand(Command):
    user_id: str
    frozen: bool
    reason: str
    actor: str
    role: str


class SetAccountFrozen(UseCase[SetAccountFrozenCommand, AccountSummary]):
    def __init__(self, *, services: AppServices, audit: AuditLog, clock: Clock) -> None:
        self._services = services
        self._audit = audit
        self._clock = clock

    def execute(self, command: SetAccountFrozenCommand) -> AccountSummary:
        if command.frozen and not command.reason.strip():
            raise InvalidInput("Un motif est requis pour geler un compte.")
        now = self._clock.now()
        captured: list[AccountSummary] = []

        def work(uow: WorkUnitOfWork) -> None:
            try:
                user = uow.users.get(EntityId(command.user_id))
            except ValueError as exc:
                raise InvalidInput("Compte introuvable.") from exc
            if user is None:
                raise InvalidInput("Compte introuvable.")
            before = user.status.value
            if command.frozen:
                user.freeze(command.reason, now)
            else:
                user.unfreeze(now)
            uow.users.save(user)
            captured.append(_summary(uow, user.id))
            self._audit.append(
                actor=command.actor,
                role=command.role,
                action="account.freeze" if command.frozen else "account.unfreeze",
                resource_type="account",
                resource_id=command.user_id,
                before={"status": before},
                after={"status": user.status.value, "reason": command.reason or None},
                now=now,
            )

        execute_in_uow(self._services.uow, self._services.events, work)
        return captured[0]


@dataclass(frozen=True, slots=True)
class ForceTransferReversalCommand(Command):
    transaction_id: str
    reason: str
    actor: str
    role: str


@dataclass(frozen=True, slots=True)
class ForcedReversalReceipt:
    reversal_id: str
    original_transaction_id: str
    reference: str
    amount_minor: int
    currency: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "reversal_id": self.reversal_id,
            "original_transaction_id": self.original_transaction_id,
            "reference": self.reference,
            "amount_minor": self.amount_minor,
            "currency": self.currency,
        }


class ForceTransferReversal(
    UseCase[ForceTransferReversalCommand, ForcedReversalReceipt]
):
    """Contre-passe un ``TRANSFER`` sans fenêtre de temps (back-office, ``finance``/
    ``admin``). Échoue si le bénéficiaire a déjà dépensé les fonds."""

    def __init__(self, *, services: AppServices, audit: AuditLog, clock: Clock) -> None:
        self._services = services
        self._audit = audit
        self._clock = clock

    def execute(
        self, command: ForceTransferReversalCommand
    ) -> ForcedReversalReceipt:
        if not command.reason.strip():
            raise InvalidInput("Un motif est requis.")
        now = self._clock.now()
        reversal_id = self._services.ids.new_id()
        captured: dict[str, Any] = {}

        def work(uow: WorkUnitOfWork) -> None:
            try:
                original = uow.ledger.get(EntityId(command.transaction_id))
            except ValueError as exc:
                raise InvalidInput("Transaction introuvable.") from exc
            if original is None:
                raise InvalidInput("Transaction introuvable.")
            if original.kind is not TransactionKind.TRANSFER:
                raise InvalidInput(
                    "Seuls les virements P2P sont contre-passables ici "
                    "(marchand / carte : utiliser leur flux dédié)."
                )
            if any(
                t.kind is TransactionKind.REVERSAL
                and t.reverses_transaction_id == original.id
                for t in uow.ledger.get_by_reference(original.reference)
            ):
                raise DuplicateOperation()

            debit = next(p for p in original.postings if p.direction is Direction.DEBIT)
            recipient_credit = next(
                p
                for p in original.postings
                if p.direction is Direction.CREDIT and p.wallet_id is not None
            )
            assert debit.wallet_id is not None and recipient_credit.wallet_id is not None
            sender_wallet = uow.wallets.get_for_update(EntityId(str(debit.wallet_id)))
            recipient_wallet = uow.wallets.get_for_update(
                EntityId(str(recipient_credit.wallet_id))
            )

            uow.ledger.add(
                LedgerTransaction.reversal(
                    id=reversal_id,
                    original=original,
                    occurred_at=now,
                    reason=f"Contre-passation back-office : {command.reason.strip()}",
                )
            )
            recipient_wallet.debit(recipient_credit.amount, now)
            sender_wallet.credit(debit.amount, now)
            uow.wallets.save(sender_wallet)
            uow.wallets.save(recipient_wallet)
            captured.update(
                reference=original.reference,
                amount=recipient_credit.amount.amount_minor,
                currency=recipient_credit.amount.currency.code,
            )
            self._audit.append(
                actor=command.actor,
                role=command.role,
                action="transaction.force_reversal",
                resource_type="ledger_transaction",
                resource_id=command.transaction_id,
                before={"reference": original.reference, "kind": original.kind.value},
                after={"reversal_id": str(reversal_id), "reason": command.reason.strip()},
                now=now,
            )

        execute_in_uow(self._services.uow, self._services.events, work)
        receipt = ForcedReversalReceipt(
            reversal_id=str(reversal_id),
            original_transaction_id=command.transaction_id,
            reference=captured["reference"],
            amount_minor=captured["amount"],
            currency=captured["currency"],
        )
        return receipt


# ------------------------------------------------------------------ notes
@dataclass(frozen=True, slots=True)
class AddAccountNoteCommand(Command):
    user_id: str
    body: str
    author: str
    role: str


@dataclass(frozen=True, slots=True)
class NoteView:
    note_id: str
    author: str
    body: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "note_id": self.note_id,
            "author": self.author,
            "body": self.body,
            "created_at": self.created_at,
        }


class AddAccountNote(UseCase[AddAccountNoteCommand, NoteView]):
    def __init__(self, *, services: AppServices, audit: AuditLog, clock: Clock) -> None:
        self._services = services
        self._audit = audit
        self._clock = clock

    def execute(self, command: AddAccountNoteCommand) -> NoteView:
        now = self._clock.now()
        note_id = self._services.ids.new_id()
        captured: list[NoteView] = []

        def work(uow: WorkUnitOfWork) -> None:
            try:
                user_id = EntityId(command.user_id)
            except ValueError as exc:
                raise InvalidInput("Compte introuvable.") from exc
            if uow.users.get(user_id) is None:
                raise InvalidInput("Compte introuvable.")
            note = SupportNote(
                id=note_id,
                subject_user_id=user_id,
                author=command.author,
                body=command.body,
                created_at=now,
            )
            uow.support_notes.add(note)
            captured.append(
                NoteView(
                    note_id=str(note.id),
                    author=note.author,
                    body=note.body,
                    created_at=note.created_at.isoformat(),
                )
            )
            self._audit.append(
                actor=command.author,
                role=command.role,
                action="account.note",
                resource_type="account",
                resource_id=command.user_id,
                before=None,
                after={"note_id": str(note_id)},
                now=now,
            )

        execute_in_uow(self._services.uow, self._services.events, work)
        return captured[0]


@dataclass(frozen=True, slots=True)
class ListAccountNotesCommand(Command):
    user_id: str


class ListAccountNotes(UseCase[ListAccountNotesCommand, list[NoteView]]):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self, command: ListAccountNotesCommand) -> list[NoteView]:
        with self._services.uow() as uow:
            try:
                user_id = EntityId(command.user_id)
            except ValueError as exc:
                raise InvalidInput("Compte introuvable.") from exc
            return [
                NoteView(
                    note_id=str(n.id),
                    author=n.author,
                    body=n.body,
                    created_at=n.created_at.isoformat(),
                )
                for n in uow.support_notes.list_for_user(user_id)
            ]


# ------------------------------------------------------------------ tickets
@dataclass(frozen=True, slots=True)
class TicketView:
    ticket_id: str
    subject_user_id: str
    subject: str
    status: str
    opened_by: str
    last_actor: str | None
    created_at: str
    updated_at: str

    @classmethod
    def of(cls, ticket: SupportTicket) -> TicketView:
        return cls(
            ticket_id=str(ticket.id),
            subject_user_id=str(ticket.subject_user_id),
            subject=ticket.subject,
            status=ticket.status.value,
            opened_by=ticket.opened_by,
            last_actor=ticket.last_actor,
            created_at=ticket.created_at.isoformat(),
            updated_at=ticket.updated_at.isoformat(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticket_id": self.ticket_id,
            "subject_user_id": self.subject_user_id,
            "subject": self.subject,
            "status": self.status,
            "opened_by": self.opened_by,
            "last_actor": self.last_actor,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True, slots=True)
class OpenSupportTicketCommand(Command):
    user_id: str
    subject: str
    actor: str
    role: str


class OpenSupportTicket(UseCase[OpenSupportTicketCommand, TicketView]):
    def __init__(self, *, services: AppServices, audit: AuditLog, clock: Clock) -> None:
        self._services = services
        self._audit = audit
        self._clock = clock

    def execute(self, command: OpenSupportTicketCommand) -> TicketView:
        now = self._clock.now()
        ticket_id = self._services.ids.new_id()
        captured: list[TicketView] = []

        def work(uow: WorkUnitOfWork) -> None:
            try:
                user_id = EntityId(command.user_id)
            except ValueError as exc:
                raise InvalidInput("Compte introuvable.") from exc
            if uow.users.get(user_id) is None:
                raise InvalidInput("Compte introuvable.")
            ticket = SupportTicket.open(
                ticket_id=ticket_id,
                subject_user_id=user_id,
                opened_by=command.actor,
                subject=command.subject,
                now=now,
            )
            uow.support_tickets.add(ticket)
            captured.append(TicketView.of(ticket))
            self._audit.append(
                actor=command.actor,
                role=command.role,
                action="ticket.open",
                resource_type="support_ticket",
                resource_id=str(ticket_id),
                before=None,
                after={"subject_user_id": command.user_id, "subject": ticket.subject},
                now=now,
            )

        execute_in_uow(self._services.uow, self._services.events, work)
        return captured[0]


@dataclass(frozen=True, slots=True)
class SetTicketStatusCommand(Command):
    ticket_id: str
    status: str
    actor: str
    role: str


class SetTicketStatus(UseCase[SetTicketStatusCommand, TicketView]):
    def __init__(self, *, services: AppServices, audit: AuditLog, clock: Clock) -> None:
        self._services = services
        self._audit = audit
        self._clock = clock

    def execute(self, command: SetTicketStatusCommand) -> TicketView:
        try:
            status = TicketStatus(command.status)
        except ValueError as exc:
            raise InvalidInput("Statut de ticket inconnu.") from exc
        now = self._clock.now()
        captured: list[TicketView] = []

        def work(uow: WorkUnitOfWork) -> None:
            try:
                ticket = uow.support_tickets.get(EntityId(command.ticket_id))
            except ValueError as exc:
                raise InvalidInput("Ticket introuvable.") from exc
            if ticket is None:
                raise InvalidInput("Ticket introuvable.")
            before = ticket.status.value
            ticket.transition_to(status, actor=command.actor, now=now)
            uow.support_tickets.save(ticket)
            captured.append(TicketView.of(ticket))
            self._audit.append(
                actor=command.actor,
                role=command.role,
                action="ticket.status",
                resource_type="support_ticket",
                resource_id=command.ticket_id,
                before={"status": before},
                after={"status": ticket.status.value},
                now=now,
            )

        execute_in_uow(self._services.uow, self._services.events, work)
        return captured[0]


@dataclass(frozen=True, slots=True)
class ListSupportTicketsCommand(Command):
    status: str | None = None
    limit: int = 100


class ListSupportTickets(UseCase[ListSupportTicketsCommand, list[TicketView]]):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self, command: ListSupportTicketsCommand) -> list[TicketView]:
        if command.status is not None:
            try:
                TicketStatus(command.status)
            except ValueError as exc:
                raise InvalidInput("Statut de ticket inconnu.") from exc
        with self._services.uow() as uow:
            return [
                TicketView.of(t)
                for t in uow.support_tickets.list_recent(
                    status=command.status, limit=max(1, min(command.limit, 500))
                )
            ]


__all__ = [
    "AccountDetail",
    "AccountSummary",
    "AddAccountNote",
    "AddAccountNoteCommand",
    "ForceTransferReversal",
    "ForceTransferReversalCommand",
    "ForcedReversalReceipt",
    "GetAccountDetail",
    "GetAccountDetailCommand",
    "LedgerLine",
    "ListAccountNotes",
    "ListAccountNotesCommand",
    "ListAccountTransactions",
    "ListAccountTransactionsCommand",
    "ListSupportTickets",
    "ListSupportTicketsCommand",
    "NoteView",
    "OpenSupportTicket",
    "OpenSupportTicketCommand",
    "SearchAccount",
    "SearchAccountCommand",
    "SetAccountFrozen",
    "SetAccountFrozenCommand",
    "SetTicketStatus",
    "SetTicketStatusCommand",
    "TicketView",
    "WalletLine",
]
