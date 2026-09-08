"""Décorateur d'authentification et accès au sujet authentifié."""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any, cast

from flask import g, request

from flash.application.auth.principal import AuthPrincipal
from flash.application.auth.tokens import TokenError
from flash.interface.security.wiring import security


class Unauthenticated(Exception):
    """En-tête d'autorisation absent ou jeton invalide/expiré/révoqué."""

    def __init__(self, message: str = "Authentification requise.") -> None:
        super().__init__(message)
        self.message = message


def _extract_bearer() -> str:
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise Unauthenticated("En-tête Authorization Bearer manquant.")
    return token.strip()


def authenticate() -> AuthPrincipal:
    """Vérifie l'access token de la requête et mémorise le sujet sur ``g``."""
    cached = g.get("principal")
    if isinstance(cached, AuthPrincipal):
        return cached
    try:
        principal = security().tokens.verify_access(_extract_bearer())
    except TokenError as exc:
        raise Unauthenticated(str(exc)) from exc
    g.principal = principal
    return principal


def current_principal() -> AuthPrincipal:
    principal = g.get("principal")
    if not isinstance(principal, AuthPrincipal):  # pragma: no cover - défensif
        raise Unauthenticated()
    return principal


def require_auth[F: Callable[..., Any]](fn: F) -> F:
    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        authenticate()
        return fn(*args, **kwargs)

    return cast("F", wrapper)


__all__ = ["Unauthenticated", "authenticate", "current_principal", "require_auth"]
