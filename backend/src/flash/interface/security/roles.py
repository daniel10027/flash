"""Rôles back-office par clé partagée (BE-062, en attendant le RBAC complet BE-075).

Chaque clé ``X-Admin-Key`` est associée à un rôle (``admin``, ``compliance``, …) via
``Deps.admin_roles``. ``require_role(*roles)`` refuse (403) toute clé absente ou dont le
rôle n'est pas dans la liste. ``require_admin`` = ``require_role("admin")``.
"""

from __future__ import annotations

import hmac
from collections.abc import Callable
from functools import wraps
from typing import Any, cast

from flask import request
from werkzeug.exceptions import Forbidden

from flash.interface.container import deps


def resolve_admin_role() -> str | None:
    provided = request.headers.get("X-Admin-Key", "").strip()
    if not provided:
        return None
    for key, role in deps().admin_roles.items():
        if key and hmac.compare_digest(key.encode(), provided.encode()):
            return role
    return None


def current_actor() -> str:
    """Identité tracée dans l'audit : pas d'utilisateur nominatif pour une clé partagée."""
    return f"key:{resolve_admin_role() or 'anonymous'}"


def require_role[F: Callable[..., Any]](*roles: str) -> Callable[[F], F]:
    allowed = frozenset(roles)

    def decorator(fn: F) -> F:
        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            role = resolve_admin_role()
            if role is None or role not in allowed:
                raise Forbidden("Accès back-office refusé.")
            return fn(*args, **kwargs)

        return cast("F", wrapper)

    return decorator


require_admin = require_role("admin")


__all__ = ["current_actor", "require_admin", "require_role", "resolve_admin_role"]
