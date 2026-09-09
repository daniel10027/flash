"""Garde ``require_card_webhook`` — authentifie les appels du réseau carte (BE-057).

Le réseau signe le corps brut de la requête : ``X-Card-Signature`` doit valoir
``hex(HMAC_SHA256(CARD_WEBHOOK_SECRET, corps))``. Sans secret configuré, l'accès est
refusé (*fail closed*).
"""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Callable
from functools import wraps
from typing import Any, cast

from flask import request
from werkzeug.exceptions import Unauthorized

from flash.interface.container import deps


def require_card_webhook[F: Callable[..., Any]](fn: F) -> F:
    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        secret = deps().card_webhook_secret.strip()
        provided = request.headers.get("X-Card-Signature", "")
        expected = hmac.new(
            secret.encode(), request.get_data(cache=True) or b"", hashlib.sha256
        ).hexdigest()
        if not secret or not hmac.compare_digest(expected, provided):
            raise Unauthorized("Signature du webhook carte invalide.")
        return fn(*args, **kwargs)

    return cast("F", wrapper)


__all__ = ["require_card_webhook"]
