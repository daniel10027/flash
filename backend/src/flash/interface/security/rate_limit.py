"""Décorateur de limitation de débit (fenêtre fixe, backend Redis)."""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any, Literal, cast

from flask import g, request

from flash.domain.shared.errors import RateLimited
from flash.interface.security.wiring import security

Subject = Literal["ip", "user", "ip+route"]


def _subject_key(subject: Subject, name: str) -> str:
    if subject == "user":
        principal = g.get("principal")
        who = str(principal.user_id) if principal is not None else _client_ip()
        return f"{name}:user:{who}"
    if subject == "ip+route":
        return f"{name}:{_client_ip()}:{request.path}"
    return f"{name}:ip:{_client_ip()}"


def _client_ip() -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    return forwarded.split(",")[0].strip() or (request.remote_addr or "unknown")


def rate_limit[F: Callable[..., Any]](
    *, name: str, limit: int, per_seconds: int, subject: Subject = "ip"
) -> Callable[[F], F]:
    """Autorise au plus ``limit`` requêtes par ``per_seconds`` et par sujet.

    Au-delà, lève ``RateLimited`` (rendu en HTTP 429 par le gestionnaire d'erreurs).
    """

    def decorator(fn: F) -> F:
        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            key = _subject_key(subject, name)
            if not security().rate_limiter.hit(key, limit=limit, per_seconds=per_seconds):
                raise RateLimited(
                    "Quota de requêtes dépassé.", limit=limit, per_seconds=per_seconds
                )
            return fn(*args, **kwargs)

        return cast("F", wrapper)

    return decorator


__all__ = ["rate_limit"]
