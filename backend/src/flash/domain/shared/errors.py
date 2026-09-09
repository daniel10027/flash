"""Erreurs de domaine.

Chaque erreur porte un ``code`` stable (SCREAMING_SNAKE_CASE) destiné aux clients et à
la documentation (``docs/api/errors.md``), un message en français, et un dictionnaire
``details`` optionnel exploitable par l'UI. La couche ``interface`` mappe ``code`` vers
un statut HTTP ; le domaine, lui, ne connaît pas HTTP.
"""

from __future__ import annotations

from typing import Any


class DomainError(Exception):
    """Racine de toutes les erreurs métier attendues (par opposition aux bugs)."""

    code: str = "DOMAIN_ERROR"
    message: str = "Erreur de domaine."

    def __init__(self, message: str | None = None, **details: Any) -> None:
        self.message = message or type(self).message
        self.details: dict[str, Any] = details
        super().__init__(self.message)

    def __str__(self) -> str:
        if self.details:
            rendered = ", ".join(f"{k}={v!r}" for k, v in self.details.items())
            return f"[{self.code}] {self.message} ({rendered})"
        return f"[{self.code}] {self.message}"


# --------------------------------------------------------------------------- argent
class InvalidInput(DomainError):
    code = "INVALID_INPUT"
    message = "Donnée fournie invalide."


class CurrencyMismatch(DomainError):
    code = "CURRENCY_MISMATCH"
    message = "Opération entre deux devises différentes."

    def __init__(self, left: str, right: str) -> None:
        super().__init__(f"Devises incompatibles : {left} et {right}.", left=left, right=right)


class InsufficientFunds(DomainError):
    code = "INSUFFICIENT_FUNDS"
    message = "Solde insuffisant pour réaliser cette opération."


class BalanceCapExceeded(DomainError):
    code = "BALANCE_CAP_EXCEEDED"
    message = "Le plafond de solde autorisé pour ce palier KYC serait dépassé."


# ------------------------------------------------------------------------- limites
class LimitExceeded(DomainError):
    code = "LIMIT_EXCEEDED"
    message = "Limite de transaction atteinte."


class KycRequired(DomainError):
    code = "KYC_REQUIRED"
    message = "Un niveau de vérification d'identité supérieur est nécessaire."

    def __init__(self, min_tier: int) -> None:
        super().__init__(
            f"Vérification d'identité requise (palier minimum : {min_tier}).",
            min_tier=min_tier,
        )


# -------------------------------------------------------------------- identité
class PhoneNumberLimitReached(DomainError):
    code = "PHONE_NUMBER_LIMIT_REACHED"
    message = "Nombre maximum de numéros atteint (5)."


class PhoneNumberAlreadyLinked(DomainError):
    code = "PHONE_NUMBER_ALREADY_LINKED"
    message = "Ce numéro est déjà rattaché à un compte."


class CannotRemoveLastPhoneNumber(DomainError):
    code = "CANNOT_REMOVE_LAST_PHONE_NUMBER"
    message = "Impossible de retirer le dernier numéro du compte."


class CannotRemovePrimaryPhoneNumber(DomainError):
    code = "CANNOT_REMOVE_PRIMARY_PHONE_NUMBER"
    message = "Définissez un autre numéro comme principal avant de retirer celui-ci."


class PhoneNumberNotFound(DomainError):
    code = "PHONE_NUMBER_NOT_FOUND"
    message = "Numéro introuvable sur ce compte."


class WalletNotFound(DomainError):
    code = "WALLET_NOT_FOUND"
    message = "Portefeuille introuvable."


class RecipientNotFound(DomainError):
    code = "RECIPIENT_NOT_FOUND"
    message = "Aucun compte Flash pour ce numéro."


class PhoneNumberNotVerified(DomainError):
    code = "PHONE_NUMBER_NOT_VERIFIED"
    message = "Ce numéro n'est pas encore vérifié."


# ----------------------------------------------------------------------- comptes
class InvalidCredentials(DomainError):
    code = "INVALID_CREDENTIALS"
    message = "Numéro ou code secret incorrect."


class UserFrozen(DomainError):
    code = "USER_FROZEN"
    message = "Ce compte est gelé."


class AccountClosed(DomainError):
    code = "ACCOUNT_CLOSED"
    message = "Ce compte est clôturé."


class InvalidAccountState(DomainError):
    code = "INVALID_ACCOUNT_STATE"
    message = "L'opération n'est pas permise dans l'état actuel du compte."


class WalletFrozen(DomainError):
    code = "WALLET_FROZEN"
    message = "Ce portefeuille est gelé."


class SelfTransfer(DomainError):
    code = "SELF_TRANSFER"
    message = "Impossible de s'envoyer de l'argent à soi-même."


class InvalidReservation(DomainError):
    code = "INVALID_RESERVATION"
    message = "Montant de réservation incohérent avec les fonds réservés."


# ------------------------------------------------------------------------- cash
class AgentFloatTooLow(DomainError):
    code = "AGENT_FLOAT_TOO_LOW"
    message = "La liquidité de l'agent est insuffisante pour cette opération."


class WithdrawalCodeInvalid(DomainError):
    code = "WITHDRAWAL_CODE_INVALID"
    message = "Code de retrait invalide."


class WithdrawalCodeExpired(DomainError):
    code = "WITHDRAWAL_CODE_EXPIRED"
    message = "Ce code de retrait a expiré."


# ------------------------------------------------------------------------ coffre
class PocketLocked(DomainError):
    code = "POCKET_LOCKED"
    message = "Cette poche du coffre est verrouillée jusqu'à sa date d'échéance."


class PocketNotEmpty(DomainError):
    code = "POCKET_NOT_EMPTY"
    message = "Impossible de supprimer une poche non vide."


# ------------------------------------------------------------- interop opérateurs
class OperatorGatewayRejected(DomainError):
    code = "OPERATOR_GATEWAY_REJECTED"
    message = "L'opérateur a refusé l'opération."


class OperatorTransferNotResolvable(DomainError):
    code = "OPERATOR_TRANSFER_NOT_RESOLVABLE"
    message = "Ce transfert opérateur n'est plus en attente."


# ------------------------------------------------------------------ API marchande
class MerchantApiKeyInvalid(DomainError):
    code = "MERCHANT_API_KEY_INVALID"
    message = "Clé d'API marchande invalide, révoquée ou marchand non habilité."


# -------------------------------------------------------------------------- carte
class CardNotActive(DomainError):
    code = "CARD_NOT_ACTIVE"
    message = "Cette carte n'est pas active."


class CardLimitReached(DomainError):
    code = "CARD_LIMIT_REACHED"
    message = "Plafond de la carte atteint."


class ChannelDisabled(DomainError):
    code = "CHANNEL_DISABLED"
    message = "Ce canal de paiement est désactivé pour cette carte."


# ------------------------------------------------------------------ reversal / idempotence
class RefundNotPossible(DomainError):
    code = "REFUND_NOT_POSSIBLE"
    message = "Le remboursement n'est pas possible (fonds déjà utilisés)."


class ReversalWindowClosed(DomainError):
    code = "REVERSAL_WINDOW_CLOSED"
    message = "Le délai d'annulation de cette opération est dépassé."


class DuplicateOperation(DomainError):
    code = "DUPLICATE_OPERATION"
    message = "Opération déjà traitée (clé d'idempotence connue)."


# ------------------------------------------------------------------ auth / OTP / débit
class OtpInvalid(DomainError):
    code = "OTP_INVALID"
    message = "Code de vérification incorrect."


class OtpTooManyAttempts(DomainError):
    code = "OTP_TOO_MANY_ATTEMPTS"
    message = "Trop de tentatives. Réessayez plus tard."


class RateLimited(DomainError):
    code = "RATE_LIMITED"
    message = "Trop de requêtes. Réessayez dans un instant."


__all__ = [name for name in dir() if name[0].isupper()]
