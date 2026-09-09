"""Cas d'usage épargne synchrones (BE-050 / BE-051 / BE-054).

Ouvrir un plan, y verser (manuellement), en retirer partiellement, le clôturer (tout est
rapatrié au portefeuille). Les versements programmés et les intérêts sont gérés par les
jobs ``application/jobs/savings.py``.

Le principal d'un plan vit dans ``wallet.saved`` : il compte dans ``wallet.balance`` mais
pas dans ``available``. Chaque mouvement est adossé à une ``LedgerTransaction`` équilibrée
(``savings_deposit`` / ``savings_withdrawal``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from flash.application.idempotency import IdempotencyGuard
from flash.application.services import AppServices
from flash.application.transaction import execute_in_uow
from flash.application.unit_of_work import WorkUnitOfWork
from flash.application.use_case import Command, UseCase
from flash.domain.ledger.chart import AccountType
from flash.domain.ledger.transaction import LedgerTransaction
from flash.domain.savings.plan import SavingsFrequency, SavingsPlan
from flash.domain.shared.errors import InvalidInput
from flash.domain.shared.identifiers import EntityId, IdempotencyKey
from flash.domain.shared.money import Money


# --------------------------------------------------------------------- vues
@dataclass(frozen=True, slots=True)
class SavingsPlanView:
    plan_id: str
    name: str
    balance_minor: int
    currency: str
    annual_rate_bps: int
    frequency: str
    contribution_minor: int
    target_minor: int | None
    target_date: str | None
    progress_bps: int | None
    accrued_interest_minor: int
    next_contribution_at: str | None
    status: str
    created_at: str

    @classmethod
    def of(cls, plan: SavingsPlan) -> SavingsPlanView:
        return cls(
            plan_id=str(plan.id),
            name=plan.name,
            balance_minor=plan.balance.amount_minor,
            currency=plan.currency.code,
            annual_rate_bps=plan.annual_rate_bps,
            frequency=plan.frequency.value,
            contribution_minor=plan.contribution.amount_minor,
            target_minor=plan.target_minor,
            target_date=plan.target_date.isoformat() if plan.target_date else None,
            progress_bps=plan.progress_bps,
            accrued_interest_minor=plan.accrued_interest_minor,
            next_contribution_at=(
                plan.next_contribution_at.isoformat() if plan.next_contribution_at else None
            ),
            status=plan.status.value,
            created_at=plan.created_at.isoformat(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "name": self.name,
            "balance_minor": self.balance_minor,
            "currency": self.currency,
            "annual_rate_bps": self.annual_rate_bps,
            "frequency": self.frequency,
            "contribution_minor": self.contribution_minor,
            "target_minor": self.target_minor,
            "target_date": self.target_date,
            "progress_bps": self.progress_bps,
            "accrued_interest_minor": self.accrued_interest_minor,
            "next_contribution_at": self.next_contribution_at,
            "status": self.status,
            "created_at": self.created_at,
        }


@dataclass(frozen=True, slots=True)
class SavingsMoveReceipt:
    plan_id: str
    plan_name: str
    direction: str  # "in" (vers l'épargne) | "out" (retour au portefeuille)
    amount_minor: int
    currency: str
    wallet_available_after_minor: int
    plan_balance_after_minor: int
    saved_after_minor: int
    occurred_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "plan_name": self.plan_name,
            "direction": self.direction,
            "amount_minor": self.amount_minor,
            "currency": self.currency,
            "wallet_available_after_minor": self.wallet_available_after_minor,
            "plan_balance_after_minor": self.plan_balance_after_minor,
            "saved_after_minor": self.saved_after_minor,
            "occurred_at": self.occurred_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SavingsMoveReceipt:
        return cls(**{k: data[k] for k in cls.__dataclass_fields__})


# --------------------------------------------------------------------- helpers
def _load_user_wallet(uow: WorkUnitOfWork, user_id: str) -> tuple[Any, Any]:
    user = uow.users.get(EntityId(user_id))
    if user is None:  # pragma: no cover - jeton valide
        raise InvalidInput("Compte introuvable.")
    user.ensure_can_transact()
    wallets = uow.wallets.list_for_user(user.id)
    if not wallets:  # pragma: no cover - un compte a toujours son portefeuille
        raise InvalidInput("Aucun portefeuille pour ce compte.")
    wallet = uow.wallets.get_for_update(EntityId(str(wallets[0].id)))
    return user, wallet


def _require_plan(uow: WorkUnitOfWork, *, plan_id: str, user_id: str) -> SavingsPlan:
    try:
        plan = uow.savings.get_for_update(EntityId(plan_id))
    except (KeyError, ValueError) as exc:
        raise InvalidInput("Plan d'épargne introuvable.") from exc
    if str(plan.user_id) != user_id:
        raise InvalidInput("Plan d'épargne introuvable.")
    return plan


def _savings_accounts(uow: WorkUnitOfWork, *, user_id: EntityId, currency: Any) -> dict[str, Any]:
    return {
        "client": uow.ledger.ensure_account(
            account_type=AccountType.CLIENT_LIABILITY, currency=currency, owner_ref=str(user_id)
        ),
        "savings": uow.ledger.ensure_account(
            account_type=AccountType.SAVINGS_LIABILITY, currency=currency, owner_ref=str(user_id)
        ),
    }


def _parse_target_date(raw: str | None) -> datetime | None:
    if raw is None or not raw.strip():
        return None
    try:
        parsed = datetime.fromisoformat(raw.strip())
    except ValueError as exc:
        raise InvalidInput("Date d'objectif invalide (format ISO 8601 attendu).") from exc
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


# ============================================================== ouvrir un plan
@dataclass(frozen=True, slots=True)
class OpenSavingsPlanCommand(Command):
    user_id: str
    name: str
    annual_rate_bps: int = 0
    frequency: str = "NONE"
    contribution_minor: int = 0
    target_minor: int | None = None
    target_date: str | None = None


class OpenSavingsPlan(UseCase[OpenSavingsPlanCommand, SavingsPlanView]):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self, command: OpenSavingsPlanCommand) -> SavingsPlanView:
        if not command.name.strip():
            raise InvalidInput("Le nom du plan est requis.")
        try:
            frequency = SavingsFrequency(command.frequency)
        except ValueError as exc:
            raise InvalidInput("Fréquence de versement inconnue.") from exc
        target_date = _parse_target_date(command.target_date)
        now = self._services.clock.now()
        plan_id = self._services.ids.new_id()
        captured: list[SavingsPlanView] = []

        def work(uow: WorkUnitOfWork) -> None:
            user, wallet = _load_user_wallet(uow, command.user_id)
            plan = SavingsPlan.open(
                plan_id=plan_id,
                wallet_id=EntityId(str(wallet.id)),
                user_id=user.id,
                currency=wallet.currency,
                name=command.name,
                now=now,
                annual_rate_bps=command.annual_rate_bps,
                frequency=frequency,
                contribution_minor=command.contribution_minor,
                target_minor=command.target_minor,
                target_date=target_date,
            )
            uow.savings.add(plan)
            captured.append(SavingsPlanView.of(plan))

        execute_in_uow(self._services.uow, self._services.events, work)
        return captured[0]


# ============================================================== consulter
@dataclass(frozen=True, slots=True)
class ListSavingsPlansCommand(Command):
    user_id: str


class ListSavingsPlans(UseCase[ListSavingsPlansCommand, list[SavingsPlanView]]):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self, command: ListSavingsPlansCommand) -> list[SavingsPlanView]:
        with self._services.uow() as uow:
            plans = uow.savings.list_for_user(EntityId(command.user_id))
            return [SavingsPlanView.of(p) for p in plans]


# ============================================================== verser / retirer
@dataclass(frozen=True, slots=True)
class ContributeToSavingsCommand(Command):
    user_id: str
    plan_id: str
    amount_minor: int
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class WithdrawFromSavingsCommand(Command):
    user_id: str
    plan_id: str
    amount_minor: int
    idempotency_key: str


class _SavingsMove:
    def __init__(self, *, services: AppServices, into_savings: bool) -> None:
        self._services = services
        self._into_savings = into_savings
        self._guard = IdempotencyGuard(services.idempotency)

    def run(
        self, *, user_id: str, plan_id: str, amount_minor: int, idempotency_key: str
    ) -> SavingsMoveReceipt:
        if amount_minor <= 0:
            raise InvalidInput("Le montant doit être strictement positif.")
        try:
            key = IdempotencyKey(idempotency_key)
        except ValueError as exc:
            raise InvalidInput(str(exc)) from exc
        route = (
            "POST /v1/savings/plans/{id}/deposit"
            if self._into_savings
            else "POST /v1/savings/plans/{id}/withdraw"
        )
        outcome = self._guard.run(
            key=key,
            subject=user_id,
            route=route,
            produce=lambda: self._move(user_id, plan_id, amount_minor),
            rebuild=SavingsMoveReceipt.from_dict,
        )
        return outcome.result

    def _move(
        self, user_id: str, plan_id: str, amount_minor: int
    ) -> tuple[SavingsMoveReceipt, dict[str, Any]]:
        now = self._services.clock.now()
        txn_id = self._services.ids.new_id()
        captured: dict[str, Any] = {}

        def work(uow: WorkUnitOfWork) -> None:
            _, wallet = _load_user_wallet(uow, user_id)
            plan = _require_plan(uow, plan_id=plan_id, user_id=user_id)
            amount = Money(amount_minor, wallet.currency)
            acc = _savings_accounts(
                uow, user_id=EntityId(str(wallet.user_id)), currency=wallet.currency
            )

            if self._into_savings:
                txn = LedgerTransaction.savings_deposit(
                    id=txn_id,
                    occurred_at=now,
                    reference=f"SAV-{txn_id}",
                    client_account_id=acc["client"],
                    savings_account_id=acc["savings"],
                    wallet_id=EntityId(str(wallet.id)),
                    plan_ref=str(plan.id),
                    amount=amount,
                    metadata={"plan_name": plan.name, "amount_minor": amount.amount_minor},
                )
                wallet.move_to_savings(amount, now)  # lève InsufficientFunds / WalletFrozen
                plan.deposit(amount, now)
            else:
                txn = LedgerTransaction.savings_withdrawal(
                    id=txn_id,
                    occurred_at=now,
                    reference=f"SAV-{txn_id}",
                    client_account_id=acc["client"],
                    savings_account_id=acc["savings"],
                    wallet_id=EntityId(str(wallet.id)),
                    plan_ref=str(plan.id),
                    amount=amount,
                    metadata={"plan_name": plan.name, "amount_minor": amount.amount_minor},
                )
                plan.withdraw(amount, now)  # lève InvalidInput si solde du plan insuffisant
                wallet.move_from_savings(amount, now)

            uow.ledger.add(txn)
            uow.wallets.save(wallet)
            uow.savings.save(plan)
            captured.update(
                plan_id=str(plan.id),
                plan_name=plan.name,
                currency=wallet.currency.code,
                available_after=wallet.available.amount_minor,
                plan_after=plan.balance.amount_minor,
                saved_after=wallet.saved.amount_minor,
            )

        execute_in_uow(self._services.uow, self._services.events, work)
        receipt = SavingsMoveReceipt(
            plan_id=captured["plan_id"],
            plan_name=captured["plan_name"],
            direction="in" if self._into_savings else "out",
            amount_minor=amount_minor,
            currency=captured["currency"],
            wallet_available_after_minor=captured["available_after"],
            plan_balance_after_minor=captured["plan_after"],
            saved_after_minor=captured["saved_after"],
            occurred_at=now.isoformat(),
        )
        return receipt, receipt.to_dict()


class ContributeToSavings(UseCase[ContributeToSavingsCommand, SavingsMoveReceipt]):
    def __init__(self, *, services: AppServices) -> None:
        self._impl = _SavingsMove(services=services, into_savings=True)

    def execute(self, command: ContributeToSavingsCommand) -> SavingsMoveReceipt:
        return self._impl.run(
            user_id=command.user_id,
            plan_id=command.plan_id,
            amount_minor=command.amount_minor,
            idempotency_key=command.idempotency_key,
        )


class WithdrawFromSavings(UseCase[WithdrawFromSavingsCommand, SavingsMoveReceipt]):
    def __init__(self, *, services: AppServices) -> None:
        self._impl = _SavingsMove(services=services, into_savings=False)

    def execute(self, command: WithdrawFromSavingsCommand) -> SavingsMoveReceipt:
        return self._impl.run(
            user_id=command.user_id,
            plan_id=command.plan_id,
            amount_minor=command.amount_minor,
            idempotency_key=command.idempotency_key,
        )


# ============================================================== clôturer
@dataclass(frozen=True, slots=True)
class CloseSavingsPlanCommand(Command):
    user_id: str
    plan_id: str


@dataclass(frozen=True, slots=True)
class CloseSavingsPlanResult:
    plan_id: str
    returned_minor: int
    currency: str
    wallet_available_after_minor: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "returned_minor": self.returned_minor,
            "currency": self.currency,
            "wallet_available_after_minor": self.wallet_available_after_minor,
        }


class CloseSavingsPlan(UseCase[CloseSavingsPlanCommand, CloseSavingsPlanResult]):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self, command: CloseSavingsPlanCommand) -> CloseSavingsPlanResult:
        now = self._services.clock.now()
        txn_id = self._services.ids.new_id()
        captured: dict[str, Any] = {}

        def work(uow: WorkUnitOfWork) -> None:
            _, wallet = _load_user_wallet(uow, command.user_id)
            plan = _require_plan(uow, plan_id=command.plan_id, user_id=command.user_id)
            returned = plan.close(now)  # lève InvalidAccountState si déjà clôturé
            if returned.is_positive:
                acc = _savings_accounts(
                    uow, user_id=EntityId(str(wallet.user_id)), currency=wallet.currency
                )
                uow.ledger.add(
                    LedgerTransaction.savings_withdrawal(
                        id=txn_id,
                        occurred_at=now,
                        reference=f"SAV-{txn_id}",
                        client_account_id=acc["client"],
                        savings_account_id=acc["savings"],
                        wallet_id=EntityId(str(wallet.id)),
                        plan_ref=str(plan.id),
                        amount=returned,
                        metadata={
                            "plan_name": plan.name,
                            "amount_minor": returned.amount_minor,
                        },
                    )
                )
                wallet.move_from_savings(returned, now)
                uow.wallets.save(wallet)
            uow.savings.save(plan)
            captured.update(
                returned=returned.amount_minor,
                currency=wallet.currency.code,
                available_after=wallet.available.amount_minor,
            )

        execute_in_uow(self._services.uow, self._services.events, work)
        return CloseSavingsPlanResult(
            plan_id=command.plan_id,
            returned_minor=captured["returned"],
            currency=captured["currency"],
            wallet_available_after_minor=captured["available_after"],
        )


__all__ = [
    "CloseSavingsPlan",
    "CloseSavingsPlanCommand",
    "CloseSavingsPlanResult",
    "ContributeToSavings",
    "ContributeToSavingsCommand",
    "ListSavingsPlans",
    "ListSavingsPlansCommand",
    "OpenSavingsPlan",
    "OpenSavingsPlanCommand",
    "SavingsMoveReceipt",
    "SavingsPlanView",
    "WithdrawFromSavings",
    "WithdrawFromSavingsCommand",
]
