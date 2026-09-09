"""Agrégat ``SavingsPlan`` — un plan d'épargne adossé à un portefeuille (BE-050).

Le principal du plan vit dans ``wallet.saved`` (donc dans ``wallet.balance`` mais hors
``available``). Chaque mouvement du plan est le reflet, dans la même Unit of Work, d'un
``Wallet.move_to_savings`` / ``move_from_savings`` / ``add_savings_interest`` **et** d'une
``LedgerTransaction`` équilibrée (``savings_deposit`` / ``savings_withdrawal`` /
``interest``). Invariant : ``Σ plan.balance == wallet.saved``.

Les intérêts sont calculés au prorata des jours écoulés (``accrue``) dans un accumulateur
sous-unité, puis capitalisés en unités entières (``capitalise``) — typiquement quotidien
pour l'accroissement, mensuel pour la capitalisation.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum

from flash.domain.savings.events import (
    SavingsContributionSkipped,
    SavingsInterestAccrued,
    SavingsInterestCapitalised,
    SavingsPlanClosed,
    SavingsPlanFunded,
    SavingsPlanOpened,
    SavingsPlanWithdrawn,
)
from flash.domain.shared.errors import InvalidAccountState, InvalidInput
from flash.domain.shared.events import EventRecorder
from flash.domain.shared.identifiers import EntityId
from flash.domain.shared.money import Currency, Money

_MAX_NAME = 60
_MICRO = 1_000_000  # échelle d'accumulation des intérêts sous l'unité mineure
_DAYS_PER_YEAR = 365
_BPS_DIVISOR = 10_000
_MAX_RATE_BPS = 2_000  # 20 % annuel — garde-fou produit
_SECONDS_PER_DAY = 86_400


class SavingsFrequency(StrEnum):
    NONE = "NONE"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"

    @property
    def period(self) -> timedelta | None:
        return {
            SavingsFrequency.WEEKLY: timedelta(days=7),
            SavingsFrequency.MONTHLY: timedelta(days=30),
        }.get(self)


class SavingsPlanStatus(StrEnum):
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"


class SavingsPlan(EventRecorder):
    def __init__(
        self,
        *,
        id: EntityId,
        wallet_id: EntityId,
        user_id: EntityId,
        currency: Currency,
        name: str,
        balance: Money,
        annual_rate_bps: int,
        frequency: SavingsFrequency,
        contribution: Money,
        created_at: datetime,
        target_minor: int | None = None,
        target_date: datetime | None = None,
        next_contribution_at: datetime | None = None,
        last_accrual_at: datetime | None = None,
        accrued_micro: int = 0,
        status: SavingsPlanStatus = SavingsPlanStatus.ACTIVE,
    ) -> None:
        super().__init__()
        if not name.strip():
            raise InvalidInput("Le nom du plan est requis.")
        if not 0 <= annual_rate_bps <= _MAX_RATE_BPS:
            raise InvalidInput(f"Taux annuel hors bornes (0 à {_MAX_RATE_BPS} points de base).")
        if target_minor is not None and target_minor <= 0:
            raise InvalidInput("L'objectif doit être strictement positif.")
        for label, money in (("balance", balance), ("contribution", contribution)):
            if money.currency != currency:
                raise InvalidInput(f"{label} n'est pas dans la devise du plan.")
            if money.is_negative:
                raise InvalidInput(f"{label} ne peut pas être négatif.")
        if frequency.period is not None and not contribution.is_positive:
            raise InvalidInput("Un versement programmé exige un montant de versement positif.")
        self.id = id
        self.wallet_id = wallet_id
        self.user_id = user_id
        self.currency = currency
        self.name = name.strip()[:_MAX_NAME]
        self.balance = balance
        self.annual_rate_bps = annual_rate_bps
        self.frequency = frequency
        self.contribution = contribution
        self.created_at = created_at
        self.target_minor = target_minor
        self.target_date = target_date
        self.next_contribution_at = next_contribution_at
        self.last_accrual_at = last_accrual_at if last_accrual_at is not None else created_at
        self._accrued_micro = max(accrued_micro, 0)
        self.status = status

    # ------------------------------------------------------------------ fabrique
    @classmethod
    def open(
        cls,
        *,
        plan_id: EntityId,
        wallet_id: EntityId,
        user_id: EntityId,
        currency: Currency,
        name: str,
        now: datetime,
        annual_rate_bps: int = 0,
        frequency: SavingsFrequency = SavingsFrequency.NONE,
        contribution_minor: int = 0,
        target_minor: int | None = None,
        target_date: datetime | None = None,
    ) -> SavingsPlan:
        contribution = Money(max(contribution_minor, 0), currency)
        period = frequency.period
        plan = cls(
            id=plan_id,
            wallet_id=wallet_id,
            user_id=user_id,
            currency=currency,
            name=name,
            balance=Money.zero(currency),
            annual_rate_bps=annual_rate_bps,
            frequency=frequency,
            contribution=contribution,
            created_at=now,
            target_minor=target_minor,
            target_date=target_date,
            next_contribution_at=(now + period) if period is not None else None,
            last_accrual_at=now,
        )
        plan.record_event(
            SavingsPlanOpened(
                occurred_at=now,
                aggregate_id=str(plan_id),
                user_id=str(user_id),
                wallet_id=str(wallet_id),
                plan_id=str(plan_id),
                plan_name=plan.name,
                annual_rate_bps=annual_rate_bps,
                frequency=frequency.value,
                contribution_minor=contribution.amount_minor,
                target_minor=target_minor,
                target_date=target_date.isoformat() if target_date else None,
            )
        )
        return plan

    # ------------------------------------------------------------------- lecture
    @property
    def is_active(self) -> bool:
        return self.status is SavingsPlanStatus.ACTIVE

    @property
    def accrued_interest_minor(self) -> int:
        """Intérêts accumulés mais pas encore capitalisés (unités entières)."""
        return self._accrued_micro // _MICRO

    @property
    def progress_bps(self) -> int | None:
        if self.target_minor is None or self.target_minor == 0:
            return None
        return min(_BPS_DIVISOR, self.balance.amount_minor * _BPS_DIVISOR // self.target_minor)

    # ----------------------------------------------------------------- garde-fous
    def _ensure_active(self) -> None:
        if not self.is_active:
            raise InvalidAccountState("Ce plan d'épargne est clôturé.")

    def _guard(self, amount: Money) -> None:
        if amount.currency != self.currency:
            raise InvalidInput("Devise du montant différente de celle du plan.")
        if not amount.is_positive:
            raise InvalidInput("Le montant doit être strictement positif.")

    # ------------------------------------------------------------------ mouvements
    def deposit(self, amount: Money, now: datetime, *, scheduled: bool = False) -> None:
        self._ensure_active()
        self._guard(amount)
        self.balance = self.balance + amount
        self.record_event(
            SavingsPlanFunded(
                occurred_at=now,
                aggregate_id=str(self.id),
                user_id=str(self.user_id),
                wallet_id=str(self.wallet_id),
                plan_id=str(self.id),
                plan_name=self.name,
                amount_minor=amount.amount_minor,
                currency=self.currency.code,
                scheduled=scheduled,
            )
        )

    def withdraw(self, amount: Money, now: datetime) -> None:
        self._ensure_active()
        self._guard(amount)
        if self.balance < amount:
            raise InvalidInput("Solde du plan insuffisant.")
        self.balance = self.balance - amount
        self.record_event(
            SavingsPlanWithdrawn(
                occurred_at=now,
                aggregate_id=str(self.id),
                user_id=str(self.user_id),
                wallet_id=str(self.wallet_id),
                plan_id=str(self.id),
                plan_name=self.name,
                amount_minor=amount.amount_minor,
                currency=self.currency.code,
            )
        )

    def close(self, now: datetime) -> Money:
        """Clôture le plan et renvoie le solde à rapatrier vers le portefeuille."""
        self._ensure_active()
        returned = self.balance
        self.balance = Money.zero(self.currency)
        self.status = SavingsPlanStatus.CLOSED
        self.record_event(
            SavingsPlanClosed(
                occurred_at=now,
                aggregate_id=str(self.id),
                user_id=str(self.user_id),
                wallet_id=str(self.wallet_id),
                plan_id=str(self.id),
                plan_name=self.name,
                amount_minor=returned.amount_minor,
                currency=self.currency.code,
            )
        )
        return returned

    # ------------------------------------------------------ versements programmés
    def contribution_due(self, now: datetime) -> bool:
        return (
            self.is_active
            and self.frequency.period is not None
            and self.next_contribution_at is not None
            and now >= self.next_contribution_at
        )

    def advance_schedule(self, now: datetime) -> None:
        """Reporte l'échéance de versement après un prélèvement (réussi ou renoncé)."""
        period = self.frequency.period
        if period is None or self.next_contribution_at is None:
            return
        nxt = self.next_contribution_at
        while nxt <= now:
            nxt = nxt + period
        self.next_contribution_at = nxt

    def skip_contribution(self, now: datetime) -> None:
        """Renonce au versement de ce cycle (solde insuffisant) et reporte l'échéance."""
        self.record_event(
            SavingsContributionSkipped(
                occurred_at=now,
                aggregate_id=str(self.id),
                user_id=str(self.user_id),
                wallet_id=str(self.wallet_id),
                plan_id=str(self.id),
                plan_name=self.name,
                amount_minor=self.contribution.amount_minor,
                currency=self.currency.code,
            )
        )
        self.advance_schedule(now)

    # ------------------------------------------------------------------ intérêts
    def accrue(self, as_of: datetime) -> int:
        """Accumule l'intérêt prorata depuis ``last_accrual_at``. Renvoie les micro-unités
        ajoutées. N'affecte pas encore le solde (voir ``capitalise``)."""
        self._ensure_active()
        elapsed = (as_of - self.last_accrual_at).total_seconds()
        if elapsed <= 0 or self.annual_rate_bps == 0 or self.balance.is_zero:
            if elapsed > 0:
                self.last_accrual_at = as_of
            return 0
        days = elapsed / _SECONDS_PER_DAY
        micro = int(
            self.balance.amount_minor
            * self.annual_rate_bps
            * _MICRO
            * days
            / (_DAYS_PER_YEAR * _BPS_DIVISOR)
        )
        self._accrued_micro += micro
        self.last_accrual_at = as_of
        if micro > 0:
            self.record_event(
                SavingsInterestAccrued(
                    occurred_at=as_of,
                    aggregate_id=str(self.id),
                    plan_id=str(self.id),
                    accrued_total_micro=self._accrued_micro,
                )
            )
        return micro

    def capitalise(self, now: datetime) -> Money:
        """Transforme les intérêts accumulés (parties entières) en solde. Peut renvoyer 0."""
        self._ensure_active()
        whole = self._accrued_micro // _MICRO
        if whole <= 0:
            return Money.zero(self.currency)
        self._accrued_micro -= whole * _MICRO
        capitalised = Money(whole, self.currency)
        self.balance = self.balance + capitalised
        self.record_event(
            SavingsInterestCapitalised(
                occurred_at=now,
                aggregate_id=str(self.id),
                user_id=str(self.user_id),
                wallet_id=str(self.wallet_id),
                plan_id=str(self.id),
                plan_name=self.name,
                amount_minor=whole,
                currency=self.currency.code,
            )
        )
        return capitalised

    @property
    def accrued_micro(self) -> int:
        """Accumulateur brut (pour la persistance)."""
        return self._accrued_micro

    def __repr__(self) -> str:
        return (
            f"SavingsPlan(id={self.id!s}, {self.currency.code}, "
            f"balance={self.balance.amount_minor}, rate={self.annual_rate_bps}bps, "
            f"status={self.status.value})"
        )


__all__ = ["SavingsFrequency", "SavingsPlan", "SavingsPlanStatus"]
