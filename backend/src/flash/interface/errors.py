"""Traduction des erreurs de domaine en réponses HTTP.

La couche ``domain`` ne connaît pas HTTP : c'est ici qu'un ``code`` stable devient un
statut. Toute erreur non mappée retombe sur 422 (règle métier non satisfaite).
"""

from __future__ import annotations

from flash.domain.shared.errors import DomainError

_STATUS_BY_CODE: dict[str, int] = {
    # 401 — authentification
    "INVALID_CREDENTIALS": 401,
    "MERCHANT_API_KEY_INVALID": 401,
    # 404 — ressource absente
    "PHONE_NUMBER_NOT_FOUND": 404,
    "WALLET_NOT_FOUND": 404,
    "RECIPIENT_NOT_FOUND": 404,
    "NOT_A_MERCHANT": 404,
    # 409 — conflit / état incompatible
    "DUPLICATE_OPERATION": 409,
    "PHONE_NUMBER_ALREADY_LINKED": 409,
    "USER_FROZEN": 409,
    "WALLET_FROZEN": 409,
    "ACCOUNT_CLOSED": 409,
    "POCKET_LOCKED": 409,
    "POCKET_NOT_EMPTY": 409,
    "CARD_NOT_ACTIVE": 409,
    "CHANNEL_DISABLED": 409,
    "REVERSAL_WINDOW_CLOSED": 409,
    "OPERATOR_TRANSFER_NOT_RESOLVABLE": 409,
    # 429 — trop de requêtes
    "RATE_LIMITED": 429,
    "OTP_TOO_MANY_ATTEMPTS": 429,
}

_DEFAULT_STATUS = 422


def status_for(error: DomainError) -> int:
    return _STATUS_BY_CODE.get(error.code, _DEFAULT_STATUS)


def to_payload(error: DomainError) -> dict[str, object]:
    return {"code": error.code, "message": error.message, "details": error.details}


__all__ = ["status_for", "to_payload"]
