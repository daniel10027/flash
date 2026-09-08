"""Plan de comptes du ledger et sens normal de chaque type de compte."""

from __future__ import annotations

from enum import StrEnum


class Direction(StrEnum):
    DEBIT = "DEBIT"
    CREDIT = "CREDIT"

    @property
    def opposite(self) -> Direction:
        return Direction.CREDIT if self is Direction.DEBIT else Direction.DEBIT


class AccountType(StrEnum):
    """Types de comptes comptables manipulés par Flash."""

    CLIENT_LIABILITY = "CLIENT_LIABILITY"  # dette de Flash envers un client (solde wallet)
    FLASH_FEE_INCOME = "FLASH_FEE_INCOME"  # produits : frais encaissés
    AGENT_FLOAT = "AGENT_FLOAT"  # e-money prépayée détenue par un agent
    AGENT_COMMISSION_EXPENSE = "AGENT_COMMISSION_EXPENSE"  # charges : commissions agents
    OPERATOR_SUSPENSE = "OPERATOR_SUSPENSE"  # transit interopérabilité opérateurs
    CARD_SCHEME_SUSPENSE = "CARD_SCHEME_SUSPENSE"  # transit réseau carte
    SAVINGS_LIABILITY = "SAVINGS_LIABILITY"  # dette envers clients : coffre + épargne
    INTEREST_EXPENSE = "INTEREST_EXPENSE"  # charges : intérêts versés sur l'épargne
    BANK_SETTLEMENT = "BANK_SETTLEMENT"  # trésorerie en banque partenaire
    MERCHANT_PAYABLE = "MERCHANT_PAYABLE"  # dette de Flash envers un marchand
    ROUNDING = "ROUNDING"  # écarts d'arrondi (conversion de devises)


# Sens normal : côté où le solde du compte augmente.
_NORMAL_BALANCE: dict[AccountType, Direction] = {
    AccountType.CLIENT_LIABILITY: Direction.CREDIT,
    AccountType.FLASH_FEE_INCOME: Direction.CREDIT,
    AccountType.AGENT_FLOAT: Direction.CREDIT,
    AccountType.AGENT_COMMISSION_EXPENSE: Direction.DEBIT,
    AccountType.OPERATOR_SUSPENSE: Direction.DEBIT,
    AccountType.CARD_SCHEME_SUSPENSE: Direction.DEBIT,
    AccountType.SAVINGS_LIABILITY: Direction.CREDIT,
    AccountType.INTEREST_EXPENSE: Direction.DEBIT,
    AccountType.BANK_SETTLEMENT: Direction.DEBIT,
    AccountType.MERCHANT_PAYABLE: Direction.CREDIT,
    AccountType.ROUNDING: Direction.CREDIT,
}


def normal_balance(account_type: AccountType) -> Direction:
    return _NORMAL_BALANCE[account_type]


__all__ = ["AccountType", "Direction", "normal_balance"]
