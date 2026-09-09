"""Garde ``require_operator_webhook`` — authentifie les callbacks opérateurs (BE-067).

Le corps brut est signé : ``X-Operator-Signature`` = ``hex(HMAC_SHA256(secret, corps))``
avec ``OPERATOR_WEBHOOK_SECRET``. Sans secret configuré, l'accès est refusé (*fail closed*).
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


def require_operator_webhook[F: Callable[..., Any]](fn: F) -> F:
    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        secret = deps().operator_webhook_secret.strip()
        provided = request.headers.get("X-Operator-Signature", "")
        expected = hmac.new(
            secret.encode(), request.get_data(cache=True) or b"", hashlib.sha256
        ).hexdigest()
        if not secret or not hmac.compare_digest(expected, provided):
            raise Unauthorized("Signature du webhook opérateur invalide.")
        return fn(*args, **kwargs)

    return cast("F", wrapper)


__all__ = ["require_operator_webhook"]
