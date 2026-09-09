"""Jobs d'épargne (BE-052 / BE-053), à appeler par cron via ``flash run-jobs``.

- ``RunScheduledSavings`` : prélève les versements programmés échus. Si le disponible est
  insuffisant, le cycle est **renoncé proprement** (``SavingsContributionSkipped`` →
  notification) et l'échéance est reportée — pas de boucle de réessai serrée.
- ``AccrueSavingsInterest`` : accroît l'intérêt au prorata des jours écoulés puis
  capitalise les unités entières acquises via ``LedgerTransaction.interest``.

Les deux sont idempotents dans les faits : relancés à la suite, ils ne trouvent plus de
versement échu / plus d'unité entière à capitaliser.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from flash.application.services import AppServices
from flash.application.transaction import execute_in_uow
from flash.application.unit_of_work import WorkUnitOfWork
from flash.domain.ledger.chart import AccountType
from flash.domain.ledger.transaction import LedgerTransaction
from flash.domain.shared.errors import InsufficientFunds
from flash.domain.shared.identifiers import EntityId

_PAGE = 500


@dataclass(frozen=True, slots=True)
class ScheduledSavingsReport:
    checked: int
    funded: int
    skipped: int

    def to_dict(self) -> dict[str, Any]:
        return {"checked": self.checked, "funded": self.funded, "skipped": self.skipped}


@dataclass(frozen=True, slots=True)
class InterestAccrualReport:
    checked: int
    capitalised_plans: int
    capitalised_minor: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "checked": self.checked,
            "capitalised_plans": self.capitalised_plans,
            "capitalised_minor": self.capitalised_minor,
        }


class RunScheduledSavings:
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self) -> ScheduledSavingsReport:
        now = self._services.clock.now()
        counts = {"checked": 0, "funded": 0, "skipped": 0}

        def work(uow: WorkUnitOfWork) -> None:
            for plan in uow.savings.list_contributions_due(now):
                counts["checked"] += 1
                wallet = uow.wallets.get_for_update(EntityId(str(plan.wallet_id)))
                amount = plan.contribution
                try:
                    wallet.move_to_savings(amount, now)
                except InsufficientFunds:
                    plan.skip_contribution(now)
                    counts["skipped"] += 1
                    uow.savings.save(plan)
                    continue

                client_acc = uow.ledger.ensure_account(
                    account_type=AccountType.CLIENT_LIABILITY,
                    currency=wallet.currency,
                    owner_ref=str(wallet.user_id),
                )
                savings_acc = uow.ledger.ensure_account(
                    account_type=AccountType.SAVINGS_LIABILITY,
                    currency=wallet.currency,
                    owner_ref=str(wallet.user_id),
                )
                txn_id = self._services.ids.new_id()
                uow.ledger.add(
                    LedgerTransaction.savings_deposit(
                        id=txn_id,
                        occurred_at=now,
                        reference=f"SAV-{txn_id}",
                        client_account_id=client_acc,
                        savings_account_id=savings_acc,
                        wallet_id=EntityId(str(wallet.id)),
                        plan_ref=str(plan.id),
                        amount=amount,
                        metadata={"plan_name": plan.name, "amount_minor": amount.amount_minor},
                    )
                )
                plan.deposit(amount, now, scheduled=True)
                plan.advance_schedule(now)
                uow.wallets.save(wallet)
                uow.savings.save(plan)
                counts["funded"] += 1

        execute_in_uow(self._services.uow, self._services.events, work)
        return ScheduledSavingsReport(
            checked=counts["checked"], funded=counts["funded"], skipped=counts["skipped"]
        )


class AccrueSavingsInterest:
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self) -> InterestAccrualReport:
        now = self._services.clock.now()
        counts = {"checked": 0, "plans": 0, "minor": 0}

        def work(uow: WorkUnitOfWork) -> None:
            after: EntityId | None = None
            while True:
                page = uow.savings.list_active(limit=_PAGE, after=after)
                if not page:
                    break
                for plan in page:
                    counts["checked"] += 1
                    plan.accrue(now)
                    capitalised = plan.capitalise(now)
                    if capitalised.is_positive:
                        wallet = uow.wallets.get_for_update(EntityId(str(plan.wallet_id)))
                        expense_acc = uow.ledger.ensure_account(
                            account_type=AccountType.INTEREST_EXPENSE, currency=wallet.currency
                        )
                        savings_acc = uow.ledger.ensure_account(
                            account_type=AccountType.SAVINGS_LIABILITY,
                            currency=wallet.currency,
                            owner_ref=str(wallet.user_id),
                        )
                        txn_id = self._services.ids.new_id()
                        uow.ledger.add(
                            LedgerTransaction.interest(
                                id=txn_id,
                                occurred_at=now,
                                reference=f"INT-{txn_id}",
                                interest_expense_account_id=expense_acc,
                                savings_account_id=savings_acc,
                                wallet_id=EntityId(str(wallet.id)),
                                plan_ref=str(plan.id),
                                amount=capitalised,
                                metadata={
                                    "plan_name": plan.name,
                                    "amount_minor": capitalised.amount_minor,
                                },
                            )
                        )
                        wallet.add_savings_interest(capitalised, now)
                        uow.wallets.save(wallet)
                        counts["plans"] += 1
                        counts["minor"] += capitalised.amount_minor
                    uow.savings.save(plan)
                if len(page) < _PAGE:
                    break
                after = EntityId(str(page[-1].id))

        execute_in_uow(self._services.uow, self._services.events, work)
        return InterestAccrualReport(
            checked=counts["checked"],
            capitalised_plans=counts["plans"],
            capitalised_minor=counts["minor"],
        )


__all__ = [
    "AccrueSavingsInterest",
    "InterestAccrualReport",
    "RunScheduledSavings",
    "ScheduledSavingsReport",
]
