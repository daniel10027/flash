"""Garde ``require_admin`` — accès back-office par clé partagée.

Solution volontairement minimale en attendant le vrai RBAC (BE-071) : l'appelant
présente l'en-tête ``X-Admin-Key`` qui doit correspondre à ``ADMIN_API_KEY``. Si la clé
n'est pas configurée, l'accès est refusé (*fail closed*).
"""

from __future__ import annotations

import hmac
from collections.abc import Callable
from functools import wraps
from typing import Any, cast

from flask import request
from werkzeug.exceptions import Forbidden

from flash.interface.container import deps


def require_admin[F: Callable[..., Any]](fn: F) -> F:
    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        expected = deps().admin_api_key
        provided = request.headers.get("X-Admin-Key", "")
        if not expected or not hmac.compare_digest(expected, provided):
            raise Forbidden("Accès back-office refusé.")
        return fn(*args, **kwargs)

    return cast("F", wrapper)


__all__ = ["require_admin"]
